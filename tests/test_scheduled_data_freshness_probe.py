from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

from app_module.update_status_history import build_update_status_history_record
import scripts.scheduled.data_freshness_probe as probe
from data_module.official_trading_calendar import OfficialTradingCalendarError
from scripts.scheduled.data_freshness_probe import main


def _patch_calendar(monkeypatch, records):
    class _Calendar:
        def __init__(self, *args, **kwargs):
            pass

        def get_recent_official_trading_days(self, reference_date, count, **kwargs):
            return records[-count:]

    monkeypatch.setattr(probe, "OfficialTradingCalendar", _Calendar)


def _write_probe_db(db_path: Path, daily_rows=(), technical_rows=()):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT)')
        conn.execute('CREATE TABLE technical_indicators ("日期" TEXT, "證券代號" TEXT)')
        conn.executemany('INSERT INTO daily_prices VALUES (?, ?)', daily_rows)
        conn.executemany('INSERT INTO technical_indicators VALUES (?, ?)', technical_rows)


def _source(payload, source_id):
    return next(item for item in payload["source_statuses"] if item["source_id"] == source_id)


def _write_quick_status(
    output_root: Path,
    *,
    run_id: str = "20260706-101",
    status: str = "passed",
    include_run_id: bool = True,
    history_path_override: str | None = None,
) -> tuple[Path, bytes, dict[str, object], dict[str, object]]:
    quick_root = output_root / "scheduled" / "data_update_quick"
    quick_root.mkdir(parents=True, exist_ok=True)
    status_path = quick_root / "latest_status.json"
    history_path = quick_root / "history.jsonl"
    payload: dict[str, object] = {
        "task": "baldr-data-update-quick-daily",
        "status": status,
        "started_at": "2026-07-06T04:55:00-07:00",
        "completed_at": "2026-07-06T05:00:00-07:00",
        "checked_at": "2026-07-06T05:00:00-07:00",
        "warnings": [],
        "errors": [],
        "steps": [],
    }
    if include_run_id:
        payload["run_id"] = run_id
    history_record: dict[str, object] = {}
    if include_run_id:
        history_record = build_update_status_history_record(
            payload,
            captured_at="2026-07-06T12:00:01+00:00",
        )
        history_path.write_text(
            json.dumps(history_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        payload["history"] = {
            "appended": True,
            "duplicate": False,
            "record_id": history_record["record_id"],
            "path": history_path_override or str(history_path),
        }
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )
    status_path.write_bytes(raw)
    return status_path, raw, payload, history_record


def _run_freshness_probe(tmp_path: Path, monkeypatch, output_root: Path) -> dict[str, object]:
    data_root = output_root.parent
    db_path = data_root / "sqlite" / "twstock.db"
    _write_probe_db(db_path)
    _patch_calendar(
        monkeypatch,
        [{
            "date_str": "2026-07-06",
            "is_trading_day": True,
            "reason_code": "test_official_open",
            "evidence": {"source": "test-calendar"},
        }],
    )
    monkeypatch.setattr(
        probe,
        "scheduled_now",
        lambda: datetime(2026, 7, 6, 5, 5, tzinfo=probe.PACIFIC),
    )
    status_path = tmp_path / "freshness.json"
    exit_code = main([
        "--data-root", str(data_root),
        "--output-root", str(output_root),
        "--db-path", str(db_path),
        "--status-path", str(status_path),
    ])
    assert exit_code == 0
    return json.loads(status_path.read_text(encoding="utf-8"))


def test_phase3c_freshness_reads_explicit_candidate_db_with_market_coverage(
    tmp_path,
) -> None:
    candidate_db = tmp_path / "candidate" / "phase3c.sqlite"
    candidate_db.parent.mkdir(parents=True)
    with sqlite3.connect(candidate_db) as conn:
        for table in ("institutional_flows", "credit_transactions"):
            conn.execute(
                f"""
                CREATE TABLE {table} (
                    stock_code TEXT NOT NULL,
                    decision_date TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    PRIMARY KEY (stock_code, decision_date)
                )
                """
            )
        conn.executemany(
            "INSERT INTO institutional_flows VALUES (?, ?, ?, ?)",
            (
                ("2330", "2026-09-21", "twse-official-T86", "2026-09-21T12:00:00+00:00"),
                ("6488", "2026-09-21", "tpex-official-3itrade", "2026-09-21T12:01:00+00:00"),
            ),
        )
        conn.executemany(
            "INSERT INTO credit_transactions VALUES (?, ?, ?, ?)",
            (
                ("2330", "2026-09-21", "twse-official-MI_MARGN", "2026-09-21T12:02:00+00:00"),
                ("6488", "2026-09-21", "tpex-official-margin_bal", "2026-09-21T12:03:00+00:00"),
            ),
        )

    statuses = probe._phase3c_candidate_statuses(
        candidate_db_path=candidate_db,
        expected_session="20260921",
    )

    institutional = next(
        item for item in statuses if item["source_id"] == "institutional_flows"
    )
    credit = next(
        item for item in statuses if item["source_id"] == "credit_transactions"
    )
    assert institutional["freshness_status"] == "current"
    assert credit["freshness_status"] == "current"
    assert institutional["candidate_only"] is True
    assert credit["candidate_only"] is True
    assert credit["frequency"] == "daily candidate source"
    assert credit["downstream"] == ["candidate research only"]
    assert credit["update_entry"] == "UpdateService.update_phase3c_candidate_range"
    assert institutional["scheduled_task"] == "baldr-data-update-quick-daily"
    assert credit["coverage"]["source_version_coverage_complete"] is True
    assert institutional["duplicate_key_count"] == 0

    stale_credit = _source(
        {
            "source_statuses": probe._phase3c_candidate_statuses(
                candidate_db_path=candidate_db,
                expected_session="20260922",
            )
        },
        "credit_transactions",
    )
    assert stale_credit["freshness_status"] == "stale"
    assert stale_credit["actual_period"] == "20260921"
    assert stale_credit["expected_period"] == "20260922"
    assert stale_credit["missing_periods"] == ["20260922"]
    assert stale_credit["reason"] == (
        "latest candidate observation is behind the expected official session"
    )


def test_freshness_probe_reports_artifact_write_failure_as_structured_error(
    tmp_path, monkeypatch, capsys
):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    sqlite_dir = data_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    db_path = sqlite_dir / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE daily_prices ("日期" TEXT)')
        conn.execute('CREATE TABLE technical_indicators ("日期" TEXT)')

    status_path = tmp_path / "freshness.json"
    log_path = tmp_path / "freshness.log"
    original_write_text = Path.write_text

    def deny_artifact_writes(path, *args, **kwargs):
        if path in {status_path, log_path}:
            raise PermissionError("artifact output denied")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", deny_artifact_writes)

    exit_code = main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
            "--status-path",
            str(status_path),
            "--log-path",
            str(log_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "status_artifact_write_failed:PermissionError" in payload["errors"]
    assert "log_artifact_write_failed:PermissionError" in payload["errors"]
    assert not status_path.exists()
    assert not log_path.exists()


def test_freshness_probe_degrades_when_tpex_file_missing_for_latest_daily_date(tmp_path, monkeypatch):
    # Keep the fixture independent from the wall clock and exercise the
    # post-cutoff branch that classifies a missing TPEx file as stale.
    monkeypatch.setattr(
        probe,
        "scheduled_now",
        lambda: datetime(2026, 7, 6, 5, 0, tzinfo=probe.PACIFIC),
    )
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    daily_price_dir = data_root / "daily_price"
    tpex_daily_price_dir = data_root / "daily_price_tpex"
    sqlite_dir = data_root / "sqlite"
    daily_price_dir.mkdir(parents=True)
    tpex_daily_price_dir.mkdir(parents=True)
    sqlite_dir.mkdir(parents=True)

    db_path = sqlite_dir / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT)')
        conn.execute('CREATE TABLE technical_indicators ("日期" TEXT, "證券代號" TEXT)')
        conn.execute('INSERT INTO daily_prices VALUES ("20260706", "2330")')
        conn.execute('INSERT INTO technical_indicators VALUES ("20260706", "2330")')

    (daily_price_dir / "20260706.csv").write_text(
        "日期,證券代號,證券名稱,收盤價\n20260706,2330,台積電,1000\n",
        encoding="utf-8-sig",
    )
    status_path = tmp_path / "status.json"

    exit_code = main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
            "--status-path",
            str(status_path),
            "--stale-days",
            "999",
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["checks"]["twse_daily_price_file_exists_for_latest_date"] is True
    assert payload["checks"]["tpex_daily_price_file_exists_for_latest_date"] is False
    assert "data_update_quick_status_missing" in payload["warnings"]
    assert "tpex_daily_price_file_missing:20260706" in payload["warnings"]
    assert "source_freshness_degraded:sqlite.daily_prices" in payload["warnings"]
    assert _source(payload, "tpex.daily_prices.raw")["freshness_status"] == "stale"


def test_freshness_probe_marks_target_waiting_before_daily_cutoff(tmp_path, monkeypatch):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    (data_root / "daily_price").mkdir(parents=True)
    (data_root / "daily_price_tpex").mkdir(parents=True)
    records = [
        {
            "date_str": value,
            "is_trading_day": True,
            "reason_code": "test_official_open",
            "evidence": {"source": "test-calendar"},
        }
        for value in ("2026-07-02", "2026-07-03", "2026-07-06")
    ]
    _patch_calendar(monkeypatch, records)
    monkeypatch.setattr(
        probe,
        "scheduled_now",
        lambda: datetime(2026, 7, 6, 4, 20, tzinfo=probe.PACIFIC),
    )
    db_path = data_root / "sqlite" / "twstock.db"
    _write_probe_db(
        db_path,
        daily_rows=[("20260703", "2330")],
        technical_rows=[("20260703", "2330")],
    )
    for directory in (data_root / "daily_price", data_root / "daily_price_tpex"):
        (directory / "20260703.csv").write_text(
            "證券代號,收盤價\n2330,1000\n",
            encoding="utf-8-sig",
        )
    status_path = tmp_path / "status.json"

    assert main([
        "--data-root", str(data_root),
        "--output-root", str(output_root),
        "--db-path", str(db_path),
        "--status-path", str(status_path),
    ]) == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert _source(payload, "twse.daily_prices.raw")["freshness_status"] == "expected_wait"
    assert _source(payload, "tpex.daily_prices.raw")["freshness_status"] == "expected_wait"
    assert _source(payload, "sqlite.daily_prices")["freshness_status"] == "expected_wait"
    assert payload["checks"]["calendar_cutoff_local"] == "04:30"


def test_freshness_probe_detects_partial_stock_reconciliation(tmp_path, monkeypatch):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    twse_dir = data_root / "daily_price"
    tpex_dir = data_root / "daily_price_tpex"
    twse_dir.mkdir(parents=True)
    tpex_dir.mkdir(parents=True)
    records = [{
        "date_str": "2026-07-06",
        "is_trading_day": True,
        "reason_code": "test_official_open",
        "evidence": {"source": "test-calendar"},
    }]
    _patch_calendar(monkeypatch, records)
    monkeypatch.setattr(
        probe,
        "scheduled_now",
        lambda: datetime(2026, 7, 6, 5, 0, tzinfo=probe.PACIFIC),
    )
    db_path = data_root / "sqlite" / "twstock.db"
    _write_probe_db(
        db_path,
        daily_rows=[("20260706", "2330")],
        technical_rows=[("20260706", "2330")],
    )
    (twse_dir / "20260706.csv").write_text(
        "證券代號,收盤價\n2330,1000\n2317,200\n",
        encoding="utf-8-sig",
    )
    (tpex_dir / "20260706.csv").write_text(
        "日期,證券代號,收盤價\n20260706,3207,42\n",
        encoding="utf-8-sig",
    )
    status_path = tmp_path / "status.json"

    assert main([
        "--data-root", str(data_root),
        "--output-root", str(output_root),
        "--db-path", str(db_path),
        "--status-path", str(status_path),
    ]) == 0

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    daily = _source(payload, "sqlite.daily_prices")
    assert daily["freshness_status"] == "partial"
    assert daily["coverage"]["reconciles_to_raw"] is False
    assert "sqlite_daily_prices_raw_reconciliation_partial" in payload["warnings"]


def test_freshness_probe_fails_closed_when_calendar_api_is_unavailable(tmp_path, monkeypatch):
    class _BrokenCalendar:
        def __init__(self, *args, **kwargs):
            pass

        def get_recent_official_trading_days(self, *args, **kwargs):
            raise OfficialTradingCalendarError("holidaySchedule unavailable")

    monkeypatch.setattr(probe, "OfficialTradingCalendar", _BrokenCalendar)
    monkeypatch.setattr(
        probe,
        "scheduled_now",
        lambda: datetime(2026, 7, 6, 5, 0, tzinfo=probe.PACIFIC),
    )
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    db_path = data_root / "sqlite" / "twstock.db"
    _write_probe_db(db_path)
    status_path = tmp_path / "status.json"

    assert main([
        "--data-root", str(data_root),
        "--output-root", str(output_root),
        "--db-path", str(db_path),
        "--status-path", str(status_path),
    ]) == 1

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert "official_calendar_unavailable" in payload["errors"]
    assert payload["checks"]["official_calendar"]["freshness_status"] == "failed"


def test_freshness_probe_degrades_when_latest_quick_update_failed(tmp_path):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    daily_price_dir = data_root / "daily_price"
    tpex_daily_price_dir = data_root / "daily_price_tpex"
    sqlite_dir = data_root / "sqlite"
    daily_price_dir.mkdir(parents=True)
    tpex_daily_price_dir.mkdir(parents=True)
    sqlite_dir.mkdir(parents=True)

    db_path = sqlite_dir / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT)')
        conn.execute('CREATE TABLE technical_indicators ("日期" TEXT, "證券代號" TEXT)')
        conn.execute('INSERT INTO daily_prices VALUES ("20260706", "2330")')
        conn.execute('INSERT INTO technical_indicators VALUES ("20260706", "2330")')

    for directory in (daily_price_dir, tpex_daily_price_dir):
        (directory / "20260706.csv").write_text("日期,證券代號\n20260706,2330\n", encoding="utf-8-sig")

    quick_status = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    quick_status.parent.mkdir(parents=True)
    quick_status.write_text(json.dumps({"status": "failed", "errors": ["TWSE download failed"]}), encoding="utf-8")
    status_path = tmp_path / "freshness.json"

    exit_code = main(
        [
            "--data-root", str(data_root),
            "--output-root", str(output_root),
            "--db-path", str(db_path),
            "--status-path", str(status_path),
            "--stale-days", "999",
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["checks"]["data_update_quick_status"] == "failed"
    assert "data_update_quick_failed" in payload["warnings"]


def test_freshness_probe_degrades_when_latest_quick_update_status_is_stale(tmp_path):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    sqlite_dir = data_root / "sqlite"
    (data_root / "daily_price").mkdir(parents=True)
    (data_root / "daily_price_tpex").mkdir(parents=True)
    sqlite_dir.mkdir(parents=True)
    db_path = sqlite_dir / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE daily_prices ("日期" TEXT)')
        conn.execute('CREATE TABLE technical_indicators ("日期" TEXT)')

    quick_status = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    quick_status.parent.mkdir(parents=True)
    quick_status.write_text(
        json.dumps({"status": "passed", "checked_at": "2000-01-01T04:20:00"}),
        encoding="utf-8",
    )
    status_path = tmp_path / "freshness.json"

    exit_code = main(
        [
            "--data-root", str(data_root),
            "--output-root", str(output_root),
            "--db-path", str(db_path),
            "--status-path", str(status_path),
        ]
    )

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["checks"]["data_update_quick_status"] == "passed"
    assert "data_update_quick_status_stale" in payload["warnings"]


def test_quick_receipt_binding_uses_same_bytes_when_latest_is_replaced(
    tmp_path, monkeypatch
):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, first_raw, first_payload, first_record = _write_quick_status(
        output_root,
        run_id="20260706-101",
    )
    _, second_raw, _, second_record = _write_quick_status(
        output_root,
        run_id="20260706-202",
    )
    history_path = quick_path.parent / "history.jsonl"
    history_path.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in (first_record, second_record)
        )
        + "\n",
        encoding="utf-8",
    )
    quick_path.write_bytes(first_raw)

    read_snapshot = probe._read_bounded_regular_file
    replaced = False

    def _replace_latest_after_read(path: Path, *, max_bytes: int) -> bytes:
        nonlocal replaced
        raw = read_snapshot(path, max_bytes=max_bytes)
        if probe._path_key(path) == probe._path_key(quick_path) and not replaced:
            quick_path.write_bytes(second_raw)
            replaced = True
        return raw

    monkeypatch.setattr(probe, "_read_bounded_regular_file", _replace_latest_after_read)
    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert replaced is True
    assert binding["binding_status"] == "verified"
    assert binding["binding_scope"] == "terminal_receipt_identity_only"
    assert binding["status_sha256"] == f"sha256:{hashlib.sha256(first_raw).hexdigest()}"
    assert binding["run_id"] == "20260706-101"
    assert binding["history_record_id"] == first_record["record_id"]
    assert binding["db_write_attribution"] is False
    assert binding["historical_pit"] is False
    assert binding["formal_credit"] is False
    assert hashlib.sha256(quick_path.read_bytes()).digest() != hashlib.sha256(first_raw).digest()
    assert payload["checks"]["data_update_quick_status"] == first_payload["status"]
    assert "data_update_quick_failed" not in payload["warnings"]
    assert "data_update_quick_status_not_successful" not in payload["warnings"]


def test_failed_quick_receipt_can_be_identity_verified_without_clearing_failure(
    tmp_path, monkeypatch
):
    output_root = tmp_path / "FA_Data" / "output"
    _write_quick_status(output_root, status="failed")

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "verified"
    assert binding["status"] == "failed"
    assert payload["checks"]["data_update_quick_status"] == "failed"
    assert "data_update_quick_failed" in payload["warnings"]
    assert "data_update_quick_status_not_successful" in payload["warnings"]


def test_legacy_quick_receipt_keeps_existing_classification_unverified(
    tmp_path, monkeypatch
):
    verified_root = tmp_path / "verified" / "FA_Data" / "output"
    legacy_root = tmp_path / "legacy" / "FA_Data" / "output"
    _write_quick_status(verified_root)
    _write_quick_status(legacy_root, include_run_id=False)

    verified = _run_freshness_probe(tmp_path / "verified", monkeypatch, verified_root)
    legacy = _run_freshness_probe(tmp_path / "legacy", monkeypatch, legacy_root)

    assert verified["checks"]["data_update_quick_receipt_binding"]["binding_status"] == "verified"
    assert legacy["checks"]["data_update_quick_receipt_binding"]["binding_status"] == "unverified"
    assert legacy["checks"]["data_update_quick_receipt_binding"]["binding_reason"] == "quick_run_id_missing"
    assert legacy["checks"]["data_update_quick_status"] == verified["checks"]["data_update_quick_status"]
    assert legacy["checks"]["data_update_quick_checked_at"] == verified["checks"]["data_update_quick_checked_at"]
    assert legacy["warnings"] == verified["warnings"]


def test_missing_quick_output_directory_keeps_existing_missing_warning(
    tmp_path, monkeypatch
):
    output_root = tmp_path / "FA_Data" / "output"

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_status_missing"
    assert payload["checks"]["data_update_quick_status"] == "missing"
    assert "data_update_quick_status_missing" in payload["warnings"]
    assert "data_update_quick_status_unreadable" not in payload["warnings"]


def test_quick_history_payload_tamper_does_not_change_freshness_rules(
    tmp_path, monkeypatch
):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, history_record = _write_quick_status(output_root)
    history_record["payload_sha256"] = "0" * 64
    (quick_path.parent / "history.jsonl").write_text(
        json.dumps(history_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_payload_or_record_hash_mismatch"
    assert payload["checks"]["data_update_quick_status"] == "passed"
    assert "data_update_quick_status_unreadable" not in payload["warnings"]


def test_quick_history_pointer_cannot_select_an_arbitrary_path(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, _ = _write_quick_status(
        output_root,
        history_path_override=str(tmp_path / "external.jsonl"),
    )

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_path_not_canonical"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_status_byte_limit_maps_to_existing_unreadable_warning(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, raw, _, _ = _write_quick_status(output_root)
    quick_path.write_bytes(raw + b" " * (probe.MAX_QUICK_STATUS_BYTES + 1))

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "receipt_file_too_large"
    assert "data_update_quick_status_unreadable" in payload["warnings"]


def test_quick_history_byte_and_record_limits_are_bounded(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, _ = _write_quick_status(output_root)
    monkeypatch.setattr(probe, "MAX_STATUS_HISTORY_BYTES", 1)

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "receipt_file_too_large"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_history_row_limit_is_bounded(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, _ = _write_quick_status(output_root)
    monkeypatch.setattr(probe, "MAX_QUICK_HISTORY_RECORD_BYTES", 32)

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_record_too_large"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_history_requires_one_terminal_record_per_run_id(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, status_payload, first_record = _write_quick_status(output_root)
    duplicate_record = build_update_status_history_record(
        {key: value for key, value in status_payload.items() if key != "history"},
        captured_at="2026-07-06T12:00:02+00:00",
    )
    history_path = quick_path.parent / "history.jsonl"
    history_path.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in (first_record, duplicate_record)
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_terminal_run_not_unique"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_status_duplicate_json_key_fails_closed(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, raw, _, _ = _write_quick_status(output_root)
    quick_path.write_bytes(
        raw[: raw.rfind(b"}")]
        + b', "run_id": "shadow-run"}\n'
    )

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_status_json_invalid"
    assert "data_update_quick_status_unreadable" in payload["warnings"]


def test_quick_status_non_finite_json_number_fails_closed(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, raw, _, _ = _write_quick_status(output_root)
    quick_path.write_bytes(
        raw[: raw.rfind(b"}")]
        + b', "unexpected_number": NaN}\n'
    )

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_status_json_invalid"
    assert "data_update_quick_status_unreadable" in payload["warnings"]


def test_quick_status_overdeep_json_fails_closed_without_crashing(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, _ = _write_quick_status(output_root)
    deep_json = b'{"nested":' + b"[" * 1200 + b"0" + b"]" * 1200 + b"}\n"
    quick_path.write_bytes(deep_json)

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_status_json_invalid"
    assert "data_update_quick_status_unreadable" in payload["warnings"]


def test_quick_history_duplicate_json_key_fails_closed(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, history_record = _write_quick_status(output_root)
    row = json.dumps(history_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    row = row[:-1] + ',"run_id":"shadow-run"}'
    (quick_path.parent / "history.jsonl").write_text(row + "\n", encoding="utf-8")

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_record_invalid"
    assert payload["checks"]["data_update_quick_status"] == "passed"
    assert "data_update_quick_status_unreadable" not in payload["warnings"]


def test_quick_history_non_finite_json_number_fails_closed(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, history_record = _write_quick_status(output_root)
    row = json.dumps(history_record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    row = row[:-1] + ',"unexpected_number":Infinity}'
    (quick_path.parent / "history.jsonl").write_text(row + "\n", encoding="utf-8")

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_record_invalid"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_history_overdeep_json_fails_closed_without_crashing(tmp_path, monkeypatch):
    output_root = tmp_path / "FA_Data" / "output"
    quick_path, _, _, _ = _write_quick_status(output_root)
    deep_json = b'{"nested":' + b"[" * 1200 + b"0" + b"]" * 1200 + b"}\n"
    (quick_path.parent / "history.jsonl").write_bytes(deep_json)

    payload = _run_freshness_probe(tmp_path, monkeypatch, output_root)

    binding = payload["checks"]["data_update_quick_receipt_binding"]
    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "quick_history_record_invalid"
    assert payload["checks"]["data_update_quick_status"] == "passed"


def test_quick_status_link_is_rejected_before_read(tmp_path):
    output_root = tmp_path / "FA_Data" / "output"
    quick_root = output_root / "scheduled" / "data_update_quick"
    quick_root.mkdir(parents=True)
    quick_path = quick_root / "latest_status.json"
    outside_path = tmp_path / "outside.json"
    outside_path.write_text("{}", encoding="utf-8")
    try:
        quick_path.symlink_to(outside_path)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")

    _, binding = probe._quick_status_snapshot(
        status_path=quick_path,
        canonical_status_path=quick_path,
        observed_at=datetime(2026, 7, 6, 5, 5, tzinfo=probe.PACIFIC),
    )

    assert binding["binding_status"] == "unverified"
    assert binding["binding_reason"] == "receipt_path_contains_link"


def test_freshness_wrapper_passes_canonical_quick_status_path():
    wrapper = (
        probe.REPO_ROOT
        / "scripts"
        / "scheduled"
        / "run_daily_data_freshness_check.ps1"
    ).read_text(encoding="utf-8")
    assert '$QuickStatusPath = Join-Path $OutputRoot "scheduled\\data_update_quick\\latest_status.json"' in wrapper
    assert "--quick-status-path $QuickStatusPath" in wrapper
