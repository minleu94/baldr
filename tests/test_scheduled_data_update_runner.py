from __future__ import annotations

from datetime import date, timezone
import json
from types import SimpleNamespace

from scripts.batch_update_daily_data import _format_update_diagnostic
from scripts.scheduled import run_daily_data_update_quick as runner
from scripts.scheduled.run_daily_data_update_quick import (
    _run_step,
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


def test_update_diagnostic_is_ascii_safe_for_windows_stdout() -> None:
    diagnostic = {
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


def test_quick_update_publishes_running_before_work_and_terminal_metadata(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
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
            runner.datetime(2026, 7, 3, 4, 20, tzinfo=timezone.utc),
            runner.datetime(2026, 7, 3, 4, 21, tzinfo=timezone.utc),
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


def test_quick_update_reports_candidate_step_when_candidate_path_is_configured(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    candidate_path = tmp_path / "candidate" / "phase3c.sqlite"
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
        update_broker_branch = _success

        def update_phase3c_candidate_range(self, **_kwargs):
            observed["candidate_calls"] += 1
            return {
                "success": True,
                "candidate_only": True,
                "candidate_db_path": str(candidate_path),
                "summary": BackfillSummary(
                    start_date="2026-07-01",
                    end_date="2026-07-03",
                    candidate_db_path=str(candidate_path),
                    dry_run=False,
                    sources=["institutional", "credit"],
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
    monkeypatch.setattr(runner, "configured_candidate_db_path", lambda: candidate_path)
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
        ]
    ) == 0
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    candidate_step = next(
        item for item in payload["steps"] if item["name"] == "update_phase3c_candidate_sources"
    )
    assert observed["candidate_calls"] == 1
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
