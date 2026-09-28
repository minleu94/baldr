from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

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
from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
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
        ]
    ) == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["optional_source_policy"] == {"skip_broker_branch": True}
    skipped = {
        item["name"]: item for item in payload["steps"] if item["status"] == "skipped"
    }
    assert skipped["update_broker_branch"]["result"]["reason"] == (
        "explicit_skip_broker_branch"
    )
    assert skipped["sync_broker_branch_to_sqlite"]["result"]["reason"] == (
        "broker_branch_refresh_skipped"
    )


def test_quick_update_reports_candidate_step_when_candidate_path_is_configured(
    tmp_path, monkeypatch
) -> None:
    _patch_capacity_preflight_for_unit_test(monkeypatch)
    _patch_verified_technical_reuse_for_metadata_unit_test(monkeypatch)
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
