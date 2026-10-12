from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from scripts.batch_update_daily_data import _format_update_diagnostic
from scripts.scheduled import run_daily_data_update_quick as runner
from scripts.scheduled.run_daily_data_update_quick import (
    _run_step,
    _update_industry_with_policy,
    _scheduled_target_weekday,
    _technical_is_current,
    _tpex_warning_messages,
    _twse_skip_warning_messages,
    _weekday_window,
)
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)
from data_module.phase3c_backfill_runner import BackfillSummary
from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from data_module.twse_industry_index_capture import (
    CSV_COLUMNS,
    atomic_write_csv_projection,
    parse_twse_industry_rows,
    persist_twse_industry_capture,
)


def _patch_capacity_preflight_for_unit_test(monkeypatch) -> None:
    """Keep runner unit tests independent from the host's live free space."""

    monkeypatch.setattr(
        runner,
        "preflight_capacity",
        lambda **_kwargs: SimpleNamespace(
            as_dict=lambda: {
                "within_budget": True,
                "required_free_bytes": 0,
                "free_bytes": 0,
                "blockers": [],
            }
        ),
    )


def _write_test_calendar_cache(cache_root: Path, *, year: int = 2026) -> Path:
    captured_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    raw_response = json.dumps(
        [
            {
                "Name": "國曆新年開始交易日",
                "Date": f"{year - 1911:03d}0102",
                "Weekday": "五",
                "Description": "國曆新年開始交易。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
    )
    cache_path = cache_root / f"twse_holiday_schedule_{year}_test.json"
    cache_root.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(
        cache_path,
        cache,
        allowed_root=cache_root.parent.parent,
    )
    return cache_path


def test_unknown_legacy_reverification_is_explicit_cli_opt_in() -> None:
    common = ["--data-root", "data", "--output-root", "output"]
    default_args = runner.build_parser().parse_args(common)
    opted_in_args = runner.build_parser().parse_args(
        common + ["--reverify-unknown-legacy-industry-dates"]
    )
    research_capture_args = runner.build_parser().parse_args(
        common + ["--capture-monthly-revenue-research-candidate"]
    )

    assert default_args.reverify_unknown_legacy_industry_dates is False
    assert opted_in_args.reverify_unknown_legacy_industry_dates is True
    assert default_args.capture_monthly_revenue_research_candidate is False
    assert research_capture_args.capture_monthly_revenue_research_candidate is True


def test_industry_policy_preserves_old_service_call_by_default() -> None:
    class LegacyService:
        def update_industry(self, start_date, end_date):
            return {"dates": (start_date, end_date)}

    class ReverificationService:
        def update_industry(
            self, start_date, end_date, *, reverify_unknown_legacy_dates=False,
        ):
            return {
                "dates": (start_date, end_date),
                "reverify": reverify_unknown_legacy_dates,
            }

    assert _update_industry_with_policy(
        LegacyService(),
        "2026-09-30",
        "2026-09-30",
        reverify_unknown_legacy_dates=False,
    ) == {"dates": ("2026-09-30", "2026-09-30")}
    assert _update_industry_with_policy(
        ReverificationService(),
        "2026-09-30",
        "2026-09-30",
        reverify_unknown_legacy_dates=True,
    ) == {"dates": ("2026-09-30", "2026-09-30"), "reverify": True}


def test_explicit_calendar_override_uses_only_supplied_caches_offline(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calendar_root = tmp_path / "qa" / "calendar"
    closure_root = tmp_path / "qa" / "temporary-closures"
    closure_root.mkdir(parents=True)
    _write_test_calendar_cache(calendar_root)
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit QA calendar must not probe online")
        ),
    )
    args = SimpleNamespace(
        calendar_cache_path=calendar_root,
        temporary_closure_path=closure_root,
        start_date="2026-09-29",
        end_date="2026-09-29",
    )
    parsed = runner.build_parser().parse_args(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(tmp_path / "output"),
            "--calendar-cache-path",
            str(calendar_root),
            "--temporary-closure-path",
            str(closure_root),
        ]
    )
    assert parsed.calendar_cache_path == calendar_root
    assert parsed.temporary_closure_path == closure_root

    calendar, allow_online_probe = runner._calendar_for_run(
        args,
        db_path=tmp_path / "missing-market.sqlite",
        reference_date=date(2026, 9, 29),
    )
    records = calendar.require_trading_days_in_range(
        date(2026, 9, 29),
        date(2026, 9, 29),
        allow_online_probe=allow_online_probe,
    )

    assert allow_online_probe is False
    assert calendar.calendar_cache_path == calendar_root.resolve()
    assert calendar.temporary_closure_path == closure_root.resolve()
    assert records[0]["is_trading_day"] is True
    scope = records[0]["evidence"]["temporary_closure_scope"]
    assert scope["status"] == "not_captured"
    assert scope["path"] == str(closure_root.resolve())
    with pytest.raises(
        runner.OfficialTradingCalendarError,
        match="does not positively resolve open session",
    ):
        runner._reject_invalid_temporary_closure_evidence(records)
    for open_record_without_evidence in (
        {"date_str": "2026-09-29", "is_trading_day": True},
        {
            "date_str": "2026-09-29",
            "is_trading_day": True,
            "evidence": "not-a-mapping",
        },
    ):
        with pytest.raises(
            runner.OfficialTradingCalendarError,
            match="evidence is missing for open session",
        ):
            runner._reject_invalid_temporary_closure_evidence(
                [open_record_without_evidence]
            )


def test_explicit_calendar_override_preflights_multiple_years_in_one_operation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calendar_root = tmp_path / "qa" / "calendar"
    closure_root = tmp_path / "qa" / "temporary-closures"
    closure_root.mkdir(parents=True)
    _write_test_calendar_cache(calendar_root, year=2026)
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit QA calendar must not probe online")
        ),
    )

    operation_options = []
    read_operation = runner.OfficialTradingCalendar.read_operation

    def track_read_operation(calendar, **kwargs):
        operation = read_operation(calendar, **kwargs)
        operation_options.append(kwargs)
        return operation

    monkeypatch.setattr(
        runner.OfficialTradingCalendar,
        "read_operation",
        track_read_operation,
    )
    args = SimpleNamespace(
        calendar_cache_path=calendar_root,
        temporary_closure_path=closure_root,
        start_date="2026-12-31",
        end_date="2027-01-04",
    )

    with pytest.raises(
        runner.OfficialTradingCalendarError,
        match="annual calendar cache unavailable for 2027",
    ):
        runner._calendar_for_run(
            args,
            db_path=tmp_path / "missing-market.sqlite",
            reference_date=date(2027, 1, 4),
        )

    assert operation_options == [{"allow_online_probe": False}]

    _write_test_calendar_cache(calendar_root, year=2027)
    operation_options.clear()
    calendar, allow_online_probe = runner._calendar_for_run(
        args,
        db_path=tmp_path / "missing-market.sqlite",
        reference_date=date(2027, 1, 4),
    )

    assert allow_online_probe is False
    assert calendar.calendar_cache_path == calendar_root.resolve()
    assert operation_options == [{"allow_online_probe": False}]


def test_explicit_calendar_override_fails_closed_but_legacy_uses_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    empty_calendar_root = tmp_path / "qa" / "empty-calendar"
    empty_calendar_root.mkdir(parents=True)
    closure_root = tmp_path / "qa" / "temporary-closures"
    closure_root.mkdir()
    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit QA calendar must not probe online")
        ),
    )
    with pytest.raises(runner.OfficialTradingCalendarError, match="annual calendar cache unavailable"):
        runner._calendar_for_run(
            SimpleNamespace(
                calendar_cache_path=empty_calendar_root,
                temporary_closure_path=closure_root,
                start_date="2026-09-29",
                end_date="2026-09-29",
            ),
            db_path=tmp_path / "missing-market.sqlite",
            reference_date=date(2026, 9, 29),
        )
    with pytest.raises(runner.OfficialTradingCalendarError, match="does not exist"):
        runner._calendar_for_run(
            SimpleNamespace(
                calendar_cache_path=empty_calendar_root / "missing",
                temporary_closure_path=None,
            ),
            db_path=tmp_path / "missing-market.sqlite",
            reference_date=date(2026, 9, 29),
        )

    valid_calendar_root = tmp_path / "qa" / "valid-calendar"
    closure_with_invalid_event = tmp_path / "qa" / "invalid-closures"
    _write_test_calendar_cache(valid_calendar_root)
    closure_with_invalid_event.mkdir()
    (closure_with_invalid_event / "twse_temporary_closure_2026-09-29.json").write_text(
        "{invalid json",
        encoding="utf-8",
    )
    explicit_calendar, allow_online_probe = runner._calendar_for_run(
        SimpleNamespace(
            calendar_cache_path=valid_calendar_root,
            temporary_closure_path=closure_with_invalid_event,
            start_date="2026-09-29",
            end_date="2026-09-29",
        ),
        db_path=tmp_path / "missing-market.sqlite",
        reference_date=date(2026, 9, 29),
    )
    records = explicit_calendar.require_trading_days_in_range(
        date(2026, 9, 29),
        date(2026, 9, 29),
        allow_online_probe=allow_online_probe,
    )
    with pytest.raises(runner.OfficialTradingCalendarError, match="evidence is invalid"):
        runner._reject_invalid_temporary_closure_evidence(records)

    default_calendar_root = tmp_path / "legacy-calendar"
    monkeypatch.setattr(runner, "_default_calendar_cache_path", lambda: default_calendar_root)
    legacy_calendar, legacy_allow_online = runner._calendar_for_run(
        SimpleNamespace(),
        db_path=tmp_path / "missing-market.sqlite",
        reference_date=date(2026, 9, 29),
    )
    assert legacy_calendar.calendar_cache_path == default_calendar_root
    assert legacy_calendar.temporary_closure_path is None
    assert legacy_allow_online is True


def test_empty_explicit_closure_cache_blocks_before_market_update_service(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "qa-data"
    output_root = tmp_path / "qa-output"
    calendar_root = tmp_path / "qa-calendar"
    closure_root = tmp_path / "empty-closure-cache"
    closure_root.mkdir()
    _write_test_calendar_cache(calendar_root)
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: datetime(2026, 9, 29, 8, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(runner, "_setup_logging", lambda _path: None)
    monkeypatch.setattr(runner, "acquire_heavy_chain_reservation", lambda _path: object())
    monkeypatch.setattr(runner, "release_heavy_chain_reservation", lambda _item: None)
    monkeypatch.setattr(
        runner,
        "configured_candidate_db_path",
        lambda: tmp_path / "qa-candidates.db",
    )
    update_service_calls: list[Path] = []
    monkeypatch.setattr(
        runner,
        "UpdateService",
        lambda config: update_service_calls.append(Path(config.db_file)),
    )
    status_path = tmp_path / "qa-status" / "quick-status.json"

    result = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--start-date",
            "2026-09-29",
            "--end-date",
            "2026-09-29",
            "--calendar-cache-path",
            str(calendar_root),
            "--temporary-closure-path",
            str(closure_root),
            "--status-path",
            str(status_path),
        ]
    )

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert result == 1
    assert update_service_calls == []
    assert status["status"] == "failed"
    assert status["writes_market_data_db"] is False
    assert "does not positively resolve open session 2026-09-29" in status["errors"][0]


def test_update_diagnostic_is_ascii_safe_for_windows_stdout() -> None:
    diagnostic: dict[str, object] = {
        "date": "2026-07-10",
        "outcome": "no_data",
        "reason_code": "twse_official_no_data",
        "request_attempts": [
            {
                "request_type": "ALLBUT0999",
                "http_status": 200,
                "api_status": "很抱歉，沒有符合條件的資料!",
            }
        ],
    }

    line = _format_update_diagnostic(diagnostic)

    line.encode("cp1252")
    assert json.loads(line.removeprefix("UPDATE_DIAGNOSTIC ")) == diagnostic


def test_run_step_converts_unexpected_service_exception_to_terminal_failure() -> None:
    steps: list[dict] = []

    failed = _run_step(
        steps=steps,
        name="unexpected_service",
        action=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert failed is not None
    assert failed["error_type"] == "RuntimeError"
    assert steps[0]["status"] == "failed"
    assert "boom" in steps[0]["message"]


def test_scheduled_target_weekday_uses_today_on_weekday() -> None:
    assert _scheduled_target_weekday(date(2026, 7, 3)) == date(2026, 7, 3)


def test_market_run_passes_one_capture_sink_to_specialized_publisher() -> None:
    capture = Path("C:/tmp/explicit-capture/manifest.json")
    calls: list[tuple[str, object]] = []

    class _Service:
        def update_market(self, start_date, end_date, *, capture_manifests):
            calls.append(("update", capture_manifests))
            capture_manifests.append(capture)
            return {"success": True, "updated_dates": [end_date]}

        def publish_taiex_market_index(self, *, capture_manifests, market_update_result):
            calls.append(("publish", (capture_manifests, market_update_result)))
            return {"success": True, "row_evidence": {"status": "captured"}}

        def sync_source_to_sqlite(self, source):
            raise AssertionError(f"generic sync must not be used: {source}")

    service = _Service()
    capture_manifests: list[Path] = []
    update_result = runner._update_market_with_capture(
        service, "2026-05-28", "2026-05-28", capture_manifests,
    )
    publish_result = runner._sync_market_index_for_run(
        service,
        capture_manifests=capture_manifests,
        market_update_result=update_result,
    )

    assert publish_result["success"] is True
    assert calls[0] == ("update", capture_manifests)
    assert calls[1] == ("publish", (capture_manifests, update_result))
    assert capture_manifests == [capture]


def test_scheduled_target_weekday_falls_back_to_friday_on_weekend() -> None:
    assert _scheduled_target_weekday(date(2026, 7, 4)) == date(2026, 7, 3)
    assert _scheduled_target_weekday(date(2026, 7, 5)) == date(2026, 7, 3)


def test_weekday_window_includes_requested_number_of_weekdays() -> None:
    start_date, end_date = _weekday_window(date(2026, 7, 3), 5)

    assert start_date == "2026-06-29"
    assert end_date == "2026-07-03"


def test_tpex_warning_messages_report_missing_failed_dates() -> None:
    warnings = _tpex_warning_messages(
        {
            "failed_dates": ["20260706"],
            "requested_dates": ["20260706"],
            "skipped_dates": [],
        }
    )

    assert warnings == ["TPEX 每日股價缺少日期：20260706"]


def test_twse_skip_warning_messages_report_explicit_no_data_dates() -> None:
    warnings = _twse_skip_warning_messages({"no_data_skipped_dates": ["2026-07-10"]})

    assert warnings == ["TWSE 官方無交易資料日（休市／颱風等），已略過日期：2026-07-10"]


def test_twse_skip_warning_messages_ignore_existing_file_skips() -> None:
    assert _twse_skip_warning_messages({"skipped_dates": ["2026-07-10"]}) == []


def test_technical_is_not_current_when_latest_date_coverage_lags() -> None:
    current, message = _technical_is_current(
        {
            "daily_data": {"latest_date": "2026-07-06"},
            "technical_indicators": {"latest_date": "2026-07-06"},
        },
        {
            "success": True,
            "is_current": False,
            "daily_latest_date": "20260706",
            "eligible_stock_count": 2,
            "covered_stock_count": 1,
        },
    )

    assert current is False
    assert "1/2" in message


def test_currentity_recompute_keeps_partial_counts_and_names_failed_stocks() -> None:
    calculation = {
        "success": False,
        "message": "技術指標計算完成：成功處理數: 2199；失敗數: 1",
        "success_count": 2199,
        "updated_stocks": ["0050", "2330"],
        "fail_count": 1,
        "failed_stocks": ["910708"],
        "sqlite_write_failed": False,
    }

    result = runner._annotate_currentity_recompute_outcome(calculation)

    assert result["success"] is False
    assert result["success_count"] == 2199
    assert result["updated_stocks"] == ["0050", "2330"]
    assert result["fail_count"] == 1
    assert result["failed_stocks"] == ["910708"]
    assert result["technical_computation_error"] == (
        "technical_currentity_recompute_partial_failure"
    )
    assert "failed_stocks=910708" in result["message"]
    assert "technical_currentity_recompute_produced_no_updates" not in result["message"]


def test_currentity_recompute_keeps_no_update_diagnostic_when_output_is_empty() -> None:
    result = runner._annotate_currentity_recompute_outcome({
        "success": False,
        "success_count": 0,
        "updated_stocks": [],
        "fail_count": 0,
        "failed_stocks": [],
        "sqlite_write_failed": False,
    })

    assert result["success"] is False
    assert result["technical_computation_error"] == (
        "technical_currentity_recompute_produced_no_updates"
    )


def test_quick_update_publishes_running_before_work_and_terminal_metadata(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    log_path = output_root / "scheduled" / "data_update_quick" / "run.log"
    observed = {"running": False}

    class _FakeUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            if not observed["running"]:
                payload = json.loads(status_path.read_text(encoding="utf-8"))
                assert payload["status"] == "running"
                assert payload["process_id"] > 0
                observed["running"] = True
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-07-03"},
                "technical_indicators": {"latest_date": "2026-07-03"},
            }

        def _success(self, *_args, **_kwargs):
            return {"success": True}

        update_daily = _success
        update_tpex_daily_price_range = _success
        sync_source_to_sqlite = _success
        update_market = _success
        update_industry = _success
        update_broker_branch = _success

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    monkeypatch.setattr(runner, "UpdateService", _FakeUpdateService)
    clock = iter(
        (
            runner.datetime(2026, 7, 3, 4, 20, 0, 100000, tzinfo=timezone.utc),
            runner.datetime(2026, 7, 3, 4, 20, 0, 900000, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: next(clock),
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
            "--log-path",
            str(log_path),
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert observed["running"] is True
    assert payload["status"] == "passed"
    assert payload["run_id"].startswith("20260703-")
    assert payload["started_at"] < payload["completed_at"]
    assert payload["started_at"] == "2026-07-03T04:20:00.100000+00:00"
    assert payload["completed_at"] == "2026-07-03T04:20:00.900000+00:00"
    assert payload["checked_at"] == payload["completed_at"]
    history_path = status_path.parent / "history.jsonl"
    history_records = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["status"] for record in history_records] == ["running", "passed"]
    assert all(record["run_id"] == payload["run_id"] for record in history_records)
    assert payload["capacity_reservation_acquired"] is True
    recovered_reservation = acquire_heavy_chain_reservation(
        output_root / "release_v4" / ".ml_heavy_chain.lock"
    )
    assert recovered_reservation is not None
    release_heavy_chain_reservation(recovered_reservation)


def test_monthly_revenue_research_capture_runs_after_capacity_release_without_changing_core(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    lock_path = output_root / "release_v4" / ".ml_heavy_chain.lock"
    history_path = status_path.parent / "history.jsonl"
    observed = {
        "capacity_released_before_capture": False,
        "release_count_at_publication": None,
        "status_bytes_before_capture": None,
    }
    real_release = runner.release_heavy_chain_reservation
    release_calls = {"count": 0}

    def tracked_release(reservation):
        if reservation is not None:
            release_calls["count"] += 1
        return real_release(reservation)

    monkeypatch.setattr(runner, "release_heavy_chain_reservation", tracked_release)

    class _FakeUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-07-03"},
                "technical_indicators": {"latest_date": "2026-07-03"},
            }

        def _success(self, *_args, **_kwargs):
            return {"success": True}

        update_daily = _success
        update_tpex_daily_price_range = _success
        sync_source_to_sqlite = _success
        update_market = _success
        update_industry = _success
        update_broker_branch = _success

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    def fail_candidate_capture(command, **kwargs):
        assert command[-1].endswith("capture_monthly_revenue_research_candidate.py")
        assert kwargs["timeout"] == 90
        assert release_calls["count"] == 1
        core_status = json.loads(status_path.read_text(encoding="utf-8"))
        assert core_status["status"] == "passed"
        assert core_status["technical_publication_receipt"]["status"] == "published"
        history_records = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert history_records[-1]["status"] == "passed"
        observed["status_bytes_before_capture"] = status_path.read_bytes()
        reservation = acquire_heavy_chain_reservation(lock_path)
        observed["capacity_released_before_capture"] = reservation is not None
        release_heavy_chain_reservation(reservation)
        return SimpleNamespace(
            returncode=2,
            stdout=json.dumps({"status": "rejected", "reason": "source_unavailable"}),
            stderr="official source timeout",
        )

    from data_module import recommendation_calibration_source_contract as source_contract

    def publish_receipt(**_kwargs):
        observed["release_count_at_publication"] = release_calls["count"]
        return {"status": "published", "path": "unit-test-technical-receipt.json"}

    monkeypatch.setattr(
        source_contract,
        "publish_technical_indicator_receipt",
        publish_receipt,
    )
    monkeypatch.setattr(runner, "UpdateService", _FakeUpdateService)
    monkeypatch.setattr(runner.subprocess, "run", fail_candidate_capture)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
    )

    exit_code = runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
            "--capture-monthly-revenue-research-candidate",
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["errors"] == []
    assert observed["release_count_at_publication"] == 0
    assert observed["capacity_released_before_capture"] is True
    assert payload["capacity_reservation_acquired"] is True
    assert payload["capacity_reservation_released_before_research_capture"] is False
    assert payload["monthly_revenue_research_capture"]["status"] == (
        "pending_after_core_publication"
    )
    receipt_path = Path(
        payload["monthly_revenue_research_capture"]["result_receipt_path"]
    )
    assert receipt_path.is_file()
    child_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert child_receipt["run_id"] == payload["run_id"]
    assert child_receipt["core_status"] == "passed"
    assert child_receipt["research_capture"]["status"] == "failed"
    assert child_receipt["research_capture"]["child_status"] == "rejected"
    assert status_path.read_bytes() == observed["status_bytes_before_capture"]


def _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch) -> None:
    """Supply custody at the boundary for fake-service metadata tests only.

    These tests do not construct a SQLite source database or exercise the
    real calculator. The production runner remains fail-closed; the mocked
    verified reuse keeps their assertions focused on status/history metadata.
    """

    from data_module import recommendation_calibration_source_contract as source_contract

    monkeypatch.setattr(
        source_contract,
        "reuse_verified_technical_computation_receipt",
        lambda **_kwargs: {
            "status": "reused",
            "technical_computation": {"fixture": "verified"},
            "source_publication_receipt": {
                "path": "unit-test-technical-receipt.json",
                "sha256": "sha256:unit-test",
                "available_at": "2026-07-03T04:00:00+00:00",
                "source_root": "unit-test-output-root",
            },
            "source_date_start": "2026-07-03",
            "source_date_end": "2026-07-03",
        },
    )


def test_quick_update_can_skip_optional_broker_branch_for_bounded_core_run(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    observed: dict[str, object] = {}

    class _FakeUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-07-03"},
                "technical_indicators": {"latest_date": "2026-07-03"},
            }

        def _success(self, *_args, **_kwargs):
            return {"success": True}

        update_daily = _success
        update_tpex_daily_price_range = _success
        sync_source_to_sqlite = _success
        update_market = _success

        def update_industry(
            self,
            start_date,
            end_date,
            *,
            reverify_unknown_legacy_dates=False,
        ):
            observed["reverify_unknown_legacy_dates"] = reverify_unknown_legacy_dates
            return {"success": True}

        def update_broker_branch(self, *_args, **_kwargs):
            raise AssertionError("optional broker branch must not run")

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    monkeypatch.setattr(runner, "UpdateService", _FakeUpdateService)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
    )

    assert runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
            "--skip-broker-branch",
            "--reverify-unknown-legacy-industry-dates",
        ]
    ) == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["optional_source_policy"] == {"skip_broker_branch": True}
    assert payload["industry_legacy_reverification_enabled"] is True
    assert observed["reverify_unknown_legacy_dates"] is True
    skipped = {
        item["name"]: item for item in payload["steps"] if item["status"] == "skipped"
    }
    assert skipped["update_broker_branch"]["result"]["reason"] == (
        "explicit_skip_broker_branch"
    )
    assert skipped["sync_broker_branch_to_sqlite"]["result"]["reason"] == (
        "broker_branch_refresh_skipped"
    )


def test_quick_update_can_skip_candidate_without_resolving_configured_path(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    observed = {"candidate_calls": 0}

    class _FakeUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-07-03"},
                "technical_indicators": {"latest_date": "2026-07-03"},
            }

        def _success(self, *_args, **_kwargs):
            return {"success": True}

        update_daily = _success
        update_tpex_daily_price_range = _success
        sync_source_to_sqlite = _success
        update_market = _success
        update_industry = _success

        def update_broker_branch(self, *_args, **_kwargs):
            raise AssertionError("the test skips the optional broker branch")

        def update_phase3c_candidate_range(self, **_kwargs):
            observed["candidate_calls"] += 1
            raise AssertionError("explicit candidate skip must not call the updater")

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    def _unexpected_candidate_path_lookup():
        raise AssertionError("explicit candidate skip must not resolve env or HKCU")

    monkeypatch.setattr(runner, "UpdateService", _FakeUpdateService)
    monkeypatch.setattr(
        runner,
        "configured_candidate_db_path",
        _unexpected_candidate_path_lookup,
    )
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
    )

    assert runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
            "--skip-broker-branch",
            "--skip-candidate-update",
        ]
    ) == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    candidate_step = next(
        item
        for item in payload["steps"]
        if item["name"] == "update_phase3c_candidate_sources"
    )
    assert payload["status"] == "passed"
    assert candidate_step["status"] == "skipped"
    assert candidate_step["result"]["reason"] == (
        "operator_requested_candidate_update_skip"
    )
    assert observed["candidate_calls"] == 0


@pytest.mark.parametrize(
    ("run_date", "expected_sources", "include_tdcc"),
    [
        (date(2026, 7, 3), ("institutional", "credit"), False),
        (date(2026, 7, 6), ("institutional", "credit", "tdcc"), True),
    ],
)
def test_quick_update_reports_candidate_step_when_candidate_path_is_configured(
    tmp_path, monkeypatch, run_date, expected_sources, include_tdcc
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    candidate_path = tmp_path / "candidate" / "phase3c.sqlite"
    observed = {"candidate_calls": 0, "configured_path_lookups": 0}

    class _Calendar:
        def get_recent_official_trading_days(self, reference_date, count, **_kwargs):
            return [{
                "date": reference_date,
                "date_str": reference_date.isoformat(),
                "is_trading_day": True,
                "reason_code": "test_verified_calendar",
                "evidence": {"source": "test-cache-and-closure-context"},
            }]

    calendar = _Calendar()

    class _FakeUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": run_date.isoformat()},
                "technical_indicators": {"latest_date": run_date.isoformat()},
            }

        def _success(self, *_args, **_kwargs):
            return {"success": True}

        update_daily = _success
        update_tpex_daily_price_range = _success
        sync_source_to_sqlite = _success
        update_market = _success
        update_industry = _success
        update_broker_branch = _success

        def update_phase3c_candidate_range(self, **_kwargs):
            observed["candidate_calls"] += 1
            observed["candidate_kwargs"] = _kwargs
            return {
                "success": True,
                "candidate_only": True,
                "candidate_db_path": str(candidate_path),
                "summary": BackfillSummary(
                    start_date=run_date.isoformat(),
                    end_date=run_date.isoformat(),
                    candidate_db_path=str(candidate_path),
                    dry_run=False,
                    sources=list(_kwargs["sources"]),
                    total_days=3,
                    trading_days_count=3,
                    non_trading_days_count=0,
                    unknown_days_count=0,
                    succeeded_days_count=3,
                    skipped_days_count=0,
                    failed_days_count=0,
                    total_rows_inserted=12,
                    tdcc_historical_status="not_requested",
                    started_at="2026-07-03T04:20:00+00:00",
                    finished_at="2026-07-03T04:20:01+00:00",
                    daily_results=[],
                ),
            }

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    monkeypatch.setattr(runner, "UpdateService", _FakeUpdateService)
    monkeypatch.setattr(
        runner,
        "_calendar_for_run",
        lambda *_args, **_kwargs: (calendar, False),
    )
    def _configured_candidate_path():
        observed["configured_path_lookups"] += 1
        return candidate_path

    monkeypatch.setattr(
        runner,
        "configured_candidate_db_path",
        _configured_candidate_path,
    )
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(
            run_date.year,
            run_date.month,
            run_date.day,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--status-path",
            str(status_path),
        ]
    ) == 0
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    candidate_step = next(
        item for item in payload["steps"] if item["name"] == "update_phase3c_candidate_sources"
    )
    assert observed["candidate_calls"] == 1
    assert observed["configured_path_lookups"] == 1
    assert observed["candidate_kwargs"]["sources"] == expected_sources
    assert observed["candidate_kwargs"]["include_latest_tdcc_snapshot"] is include_tdcc
    assert observed["candidate_kwargs"]["calendar"] is calendar
    assert observed["candidate_kwargs"]["allow_online_calendar_probe"] is False
    assert candidate_step["status"] == "passed"
    assert candidate_step["result"]["candidate_only"] is True
    assert candidate_step["result"]["summary"]["succeeded_days_count"] == 3
    history_records = [
        json.loads(line)
        for line in (status_path.parent / "history.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["status"] for record in history_records] == ["running", "passed"]


def test_quick_update_releases_capacity_reservation_after_service_exception(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    lock_path = tmp_path / "shared" / ".ml_heavy_chain.lock"

    class _RaisingUpdateService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            raise RuntimeError("service exploded")

    monkeypatch.setattr(runner, "UpdateService", _RaisingUpdateService)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
    )

    assert runner.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--capacity-lock-path",
            str(lock_path),
            "--status-path",
            str(status_path),
        ]
    ) == 1
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert "service exploded" in payload["errors"][0]
    recovered = acquire_heavy_chain_reservation(lock_path)
    assert recovered is not None
    release_heavy_chain_reservation(recovered)


def test_quick_update_fails_before_service_when_shared_capacity_lock_is_busy(
    tmp_path, monkeypatch
) -> None:
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    lock_path = tmp_path / "shared" / ".ml_heavy_chain.lock"
    held = acquire_heavy_chain_reservation(lock_path)
    assert held is not None

    class _UnexpectedUpdateService:
        def __init__(self, _config) -> None:
            raise AssertionError("service must not start while capacity lock is busy")

    monkeypatch.setattr(runner, "UpdateService", _UnexpectedUpdateService)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
    )
    try:
        assert runner.main(
            [
                "--data-root",
                str(data_root),
                "--output-root",
                str(output_root),
                "--capacity-lock-path",
                str(lock_path),
                "--status-path",
                str(status_path),
            ]
        ) == 2
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        assert payload["status"] == "failed"
        assert payload["writes_market_data_db"] is False
        assert payload["capacity_preflight"]["blocker"] == (
            "shared_capacity_reservation_unavailable"
        )
    finally:
        release_heavy_chain_reservation(held)


def _patch_isolated_industry_runner(monkeypatch, *, trading_dates: list[str]) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
    allowed_dates = set(trading_dates)

    class _Calendar:
        def __init__(self, **_kwargs) -> None:
            pass

        def require_trading_days_in_range(self, start, end, **_kwargs):
            requested = [day.isoformat() for day in date_range(start, end)]
            assert set(requested).issubset(allowed_dates)
            return [
                {"date_str": day, "calendar_source": "isolated-test"}
                for day in requested
            ]

    def date_range(start: date, end: date):
        from datetime import timedelta

        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    monkeypatch.setattr(runner, "OfficialTradingCalendar", _Calendar)
    monkeypatch.setattr(runner, "configured_candidate_db_path", lambda: None)
    monkeypatch.setattr(
        runner,
        "scheduled_now",
        lambda: runner.datetime(2026, 9, 4, 4, 0, tzinfo=timezone.utc),
    )
    from data_module import recommendation_calibration_source_contract as source_contract

    monkeypatch.setattr(
        source_contract,
        "publish_technical_indicator_receipt",
        lambda **_kwargs: {"status": "isolated_test_not_requested"},
    )


def _seed_industry_runner_files(config: TWStockConfig) -> None:
    config.industry_index_file.parent.mkdir(parents=True, exist_ok=True)
    with config.industry_index_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "指數名稱": "電子工業類指數",
                    "收盤指數": "90",
                    "漲跌": "+",
                    "漲跌點數": "1",
                    "漲跌百分比": "1",
                    "日期": "2026-09-02",
                },
                {
                    "指數名稱": "電子工業類指數",
                    "收盤指數": "1",
                    "漲跌": "-",
                    "漲跌點數": "99",
                    "漲跌百分比": "99",
                    "日期": "2026-09-03",
                },
                {
                    "指數名稱": "舊失敗日資料",
                    "收盤指數": "77",
                    "漲跌": "+",
                    "漲跌點數": "2",
                    "漲跌百分比": "2",
                    "日期": "2026-09-04",
                },
            ]
        )
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            """CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                漲跌 TEXT,
                漲跌點數 REAL,
                漲跌百分比 REAL
            )"""
        )
        connection.executemany(
            'INSERT INTO industry_indices VALUES (?, ?, ?, ?, ?, ?)',
            [
                ("20260902", "電子工業類指數", 90, "+", 1, 1),
                ("20260903", "電子工業類指數", 1, "-", 99, 99),
                ("20260904", "舊失敗日資料", 77, "+", 2, 2),
            ],
        )


@pytest.mark.parametrize(
    "batch_mode",
    ["partial_return", "exception_after_capture", "exception_without_capture"],
)
def test_quick_runner_scoped_syncs_partial_industry_capture_but_stays_failed(
    tmp_path, monkeypatch, batch_mode,
) -> None:
    """The runner publishes successful captured dates before terminal failure."""

    _patch_isolated_industry_runner(monkeypatch, trading_dates=["2026-09-03", "2026-09-04"])
    data_root = tmp_path / "qa-data"
    output_root = tmp_path / "qa-output"
    status_path = output_root / "scheduled" / "quick" / "latest_status.json"
    config = TWStockConfig(data_root=data_root, output_root=output_root)
    _seed_industry_runner_files(config)

    payload = {
        "stat": "OK",
        "date": "115年09月03日",
        "tables": [{
            "title": "115年09月03日 類股指數",
            "rows": [
                ["電子工業類指數", "100.25", "<p>+</p>", "1.00", "0.50"],
                ["觀光餐旅類指數", "200.75", "<p>-</p>", "2.00", "1.25"],
            ],
        }],
    }
    service_state: dict[str, object] = {"scoped_calls": [], "generic_industry": 0}

    class _PartialIndustryService(UpdateService):
        def __init__(self, service_config) -> None:
            super().__init__(service_config)
            self.scripts_dir = output_root / "isolated-scripts"
            self.scripts_dir.mkdir(parents=True, exist_ok=True)
            (self.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
                "# isolated fake batch entrypoint\n",
                encoding="utf-8",
            )

        def check_data_overview(self):
            current = json.loads(status_path.read_text(encoding="utf-8"))
            assert current["status"] == "running"
            assert current["run_id"] != "stale-success-run"
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-09-04"},
                "technical_indicators": {"latest_date": "2026-09-04"},
            }

        def update_daily(self, *_args, **_kwargs):
            return {"success": True}

        def update_tpex_daily_price_range(self, *_args, **_kwargs):
            return {"success": True}

        def sync_source_to_sqlite(self, source, *_args, **_kwargs):
            if source == "industry_index":
                service_state["generic_industry"] = int(service_state["generic_industry"]) + 1
                return {"success": False, "message": "legacy sync must not run"}
            return {"success": True}

        def update_market(self, *_args, **_kwargs):
            return {"success": True}

        def publish_taiex_market_index(self, **_kwargs):
            return {"success": True, "skipped": True}

        def sync_industry_index_captures_to_sqlite(self, *args, **kwargs):
            calls = service_state["scoped_calls"]
            assert isinstance(calls, list)
            calls.append((args, kwargs))
            return super().sync_industry_index_captures_to_sqlite(*args, **kwargs)

        def update_broker_branch(self, *_args, **_kwargs):
            raise AssertionError("steps after partial industry failure must not run")

    import importlib.util

    class _BatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def fake_batch_update(
                *, start_date, end_date, config, capture_manifests, batch_outcome,
            ):
                if batch_mode == "exception_without_capture":
                    raise RuntimeError("simulated exception before any capture")
                rows = parse_twse_industry_rows(payload, start_date)
                capture = persist_twse_industry_capture(
                    output_root=config.output_root,
                    source_date=start_date,
                    requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                    final_url=(
                        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                        f"?date={start_date.replace('-', '')}&type=IND&response=json"
                    ),
                    request_parameters={
                        "date": start_date.replace("-", ""),
                        "type": "IND",
                        "response": "json",
                    },
                    http_status=200,
                    response_headers={"content-type": "application/json"},
                    raw_response=json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8"),
                    captured_at=datetime(2026, 9, 4, 4, 0, tzinfo=timezone.utc),
                    parse_status="accepted",
                    parse_reason=None,
                    response_date_status="verified",
                    completeness_status="accepted",
                    completeness_reason=None,
                    selected_table_titles=["115年09月03日 類股指數"],
                    rows=rows,
                )
                atomic_write_csv_projection(
                    config.industry_index_file,
                    start_date,
                    rows,
                    skip_backup=True,
                    config=config,
                )
                capture_manifests.append(Path(str(capture["path"])))
                if batch_mode == "exception_after_capture":
                    raise RuntimeError("simulated exception after first capture")
                batch_outcome.update({
                    "success": False,
                    "updated_dates": [start_date],
                    "failed_dates": [end_date],
                })
                return False

            module.batch_update_industry_index = fake_batch_update

    real_spec_from_file_location = importlib.util.spec_from_file_location

    def isolated_batch_spec(name, location, *args, **kwargs):
        if name == "batch_update_market_and_industry_index":
            return importlib.util.spec_from_loader(name, _BatchLoader())
        return real_spec_from_file_location(name, location, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", isolated_batch_spec)
    monkeypatch.setattr(runner, "UpdateService", _PartialIndustryService)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({
            "status": "passed",
            "run_id": "stale-success-run",
            "steps": [{
                "name": "sync_industry_index_to_sqlite",
                "result": {"capture_manifests": ["old-success.json"]},
            }],
        }),
        encoding="utf-8",
    )

    exit_code = runner.main(
        [
            "--data-root", str(data_root),
            "--output-root", str(output_root),
            "--status-path", str(status_path),
            "--start-date", "2026-09-03",
            "--end-date", "2026-09-04",
        ]
    )

    terminal = json.loads(status_path.read_text(encoding="utf-8"))
    steps = {item["name"]: item for item in terminal["steps"]}
    assert exit_code == 1
    assert terminal["status"] == "failed"
    assert terminal["run_id"] != "stale-success-run"
    assert steps["update_industry_index"]["status"] == "failed"
    scoped_calls = service_state["scoped_calls"]
    assert isinstance(scoped_calls, list)
    update_result = steps["update_industry_index"]["result"]
    assert update_result["success"] is False
    assert "sync_industry_index_to_sqlite" not in steps
    assert "update_broker_branch" not in steps
    assert "calculate_technical_indicators" not in steps
    assert service_state["generic_industry"] == 0

    if batch_mode == "exception_without_capture":
        assert update_result["partial"] is False
        assert update_result["capture_manifests"] == []
        assert update_result["updated_dates"] == []
        assert update_result["failed_dates"] == []
        assert update_result["failure_date_unknown"] is True
        assert update_result["failure_reason_code"] == "batch_exception_without_capture"
        assert "sync_industry_index_partial_captures_to_sqlite" not in steps
        assert scoped_calls == []
        with sqlite3.connect(config.db_file) as connection:
            rows = connection.execute(
                'SELECT "日期", "指數名稱", "收盤指數" FROM industry_indices '
                'ORDER BY "日期", "指數名稱"'
            ).fetchall()
        assert rows == [
            ("20260902", "電子工業類指數", 90.0),
            ("20260903", "電子工業類指數", 1.0),
            ("20260904", "舊失敗日資料", 77.0),
        ]
        return

    assert update_result["partial"] is True
    assert update_result["updated_dates"] == ["2026-09-03"]
    if batch_mode == "exception_after_capture":
        assert update_result["capture_manifests"]
        assert update_result["failed_dates"] == []
        assert update_result["failure_date_unknown"] is True
        assert update_result["failure_reason_code"] == "batch_exception_after_capture"
        assert update_result["failure_date_range"] == {
            "start_date": "2026-09-03",
            "end_date": "2026-09-04",
        }
        assert "exact failed date unknown" in update_result["partial_reason"]
    else:
        assert update_result["failed_dates"] == ["2026-09-04"]
        assert "failure_date_unknown" not in update_result

    assert steps["sync_industry_index_partial_captures_to_sqlite"]["status"] == "passed"
    partial_sync = steps["sync_industry_index_partial_captures_to_sqlite"]["result"]
    assert partial_sync["success"] is True
    assert partial_sync["partial"] is True
    assert partial_sync["dates"] == ["2026-09-03"]
    expected_failed_dates = [] if batch_mode == "exception_after_capture" else ["2026-09-04"]
    assert partial_sync["failed_dates"] == expected_failed_dates
    assert Path(partial_sync["projection_commit_marker"]).is_file()
    marker_payload = json.loads(
        Path(partial_sync["projection_commit_marker"]).read_text(encoding="utf-8")
    )
    assert marker_payload["batch_scope_status"] == "partial"
    assert marker_payload["failed_dates"] == expected_failed_dates
    from data_module.twse_industry_index_capture import verified_industry_projection_dates

    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}
    assert len(scoped_calls) == 1
    assert scoped_calls[0][1] == {
        "batch_partial": True,
        "failed_dates": expected_failed_dates,
        "unknown_legacy_dates": [],
    }
    with sqlite3.connect(config.db_file) as connection:
        rows = connection.execute(
            'SELECT "日期", "指數名稱", "收盤指數" FROM industry_indices '
            'ORDER BY "日期", "指數名稱"'
        ).fetchall()
    assert rows == [
        ("20260902", "電子工業類指數", 90.0),
        ("20260903", "觀光餐旅類指數", 200.75),
        ("20260903", "電子工業類指數", 100.25),
        ("20260904", "舊失敗日資料", 77.0),
    ]


def test_quick_runner_does_not_sync_legacy_failed_industry_without_capture(
    tmp_path, monkeypatch
) -> None:
    _patch_isolated_industry_runner(monkeypatch, trading_dates=["2026-09-03"])
    data_root = tmp_path / "qa-data"
    output_root = tmp_path / "qa-output"
    status_path = output_root / "scheduled" / "quick" / "latest_status.json"
    observed: dict[str, object] = {"industry_syncs": 0}

    class _LegacyFailureService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-09-03"},
                "technical_indicators": {"latest_date": "2026-09-03"},
            }

        def update_daily(self, *_args, **_kwargs):
            return {"success": True}

        def update_tpex_daily_price_range(self, *_args, **_kwargs):
            return {"success": True}

        def sync_source_to_sqlite(self, source, *_args, **_kwargs):
            if source == "industry_index":
                observed["industry_syncs"] = int(observed["industry_syncs"]) + 1
            return {"success": True}

        def update_market(self, *_args, **_kwargs):
            return {"success": True}

        def publish_taiex_market_index(self, **_kwargs):
            return {"success": True}

        def update_industry(self, *_args, **_kwargs):
            return {
                "success": False,
                "partial": False,
                "message": "legacy update failed",
                "failed_dates": ["2026-09-03"],
                "capture_manifests": [],
            }

        def update_broker_branch(self, *_args, **_kwargs):
            raise AssertionError("steps after update failure must not run")

    monkeypatch.setattr(runner, "UpdateService", _LegacyFailureService)
    exit_code = runner.main(
        [
            "--data-root", str(data_root),
            "--output-root", str(output_root),
            "--status-path", str(status_path),
            "--start-date", "2026-09-03",
            "--end-date", "2026-09-03",
        ]
    )

    terminal = json.loads(status_path.read_text(encoding="utf-8"))
    step_names = [item["name"] for item in terminal["steps"]]
    assert exit_code == 1
    assert terminal["status"] == "failed"
    assert terminal["steps"][-1]["result"]["failed_dates"] == ["2026-09-03"]
    assert "sync_industry_index_to_sqlite" not in step_names
    assert "sync_industry_index_partial_captures_to_sqlite" not in step_names
    assert observed["industry_syncs"] == 0


def test_quick_runner_keeps_verified_industry_noop_on_legacy_sync_path(
    tmp_path, monkeypatch
) -> None:
    _patch_isolated_industry_runner(monkeypatch, trading_dates=["2026-09-03"])
    data_root = tmp_path / "qa-data"
    output_root = tmp_path / "qa-output"
    status_path = output_root / "scheduled" / "quick" / "latest_status.json"
    industry_sync_results: list[dict[str, object]] = []

    class _VerifiedNoopService:
        def __init__(self, _config) -> None:
            pass

        def check_data_overview(self):
            return {
                "success": True,
                "daily_data": {"latest_date": "2026-09-03"},
                "technical_indicators": {"latest_date": "2026-09-03"},
            }

        def update_daily(self, *_args, **_kwargs):
            return {"success": True}

        def update_tpex_daily_price_range(self, *_args, **_kwargs):
            return {"success": True}

        def sync_source_to_sqlite(self, source, *_args, **_kwargs):
            if source == "industry_index":
                result = {
                    "success": True,
                    "skipped": True,
                    "reason": "verified_industry_projection_current",
                }
                industry_sync_results.append(result)
                return result
            return {"success": True}

        def update_market(self, *_args, **_kwargs):
            return {"success": True}

        def publish_taiex_market_index(self, **_kwargs):
            return {"success": True}

        def update_industry(self, *_args, **_kwargs):
            return {
                "success": True,
                "partial": False,
                "message": "all dates already have verified projections",
                "verified_skipped_dates": ["2026-09-03"],
                "failed_dates": [],
                "capture_manifests": [],
            }

        def check_technical_indicator_latest_coverage(self):
            return {"success": True, "is_current": True}

    monkeypatch.setattr(runner, "UpdateService", _VerifiedNoopService)
    exit_code = runner.main(
        [
            "--data-root", str(data_root),
            "--output-root", str(output_root),
            "--status-path", str(status_path),
            "--start-date", "2026-09-03",
            "--end-date", "2026-09-03",
            "--skip-broker-branch",
        ]
    )

    terminal = json.loads(status_path.read_text(encoding="utf-8"))
    steps = {item["name"]: item for item in terminal["steps"]}
    assert exit_code == 0
    assert terminal["status"] == "passed"
    assert steps["update_industry_index"]["result"]["verified_skipped_dates"] == [
        "2026-09-03"
    ]
    assert steps["sync_industry_index_to_sqlite"]["status"] == "passed"
    assert steps["sync_industry_index_to_sqlite"]["result"]["skipped"] is True
    assert len(industry_sync_results) == 1
    assert "sync_industry_index_partial_captures_to_sqlite" not in steps
