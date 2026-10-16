from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import app_module.workbench_source_service as workbench_source_service_module
from app_module.pre_v2_readiness_service import PreV2ReadinessReport
from app_module.workbench_read_only_composer import WorkbenchReadOnlyComposer
from app_module.workbench_source_service import WorkbenchSourceService
from tests.decision_capture_status_fixture import (
    create_decision_capture_fixture,
    create_prelaunch_failure_fixture,
)


def test_composer_uses_injected_taipei_clock_without_snapshot() -> None:
    evaluation_at = datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc)
    readiness = PreV2ReadinessReport(
        generated_at="2026-10-06T16:00:00+00:00",
        overall_status="blocked",
        production_scheduler_allowed=False,
        items=(),
        limitations=(),
    )

    dashboard = WorkbenchReadOnlyComposer(clock=lambda: evaluation_at).compose(
        decision_snapshot=None,
        readiness_report=readiness,
    )

    assert dashboard.as_of_date == date(2026, 10, 7)
    assert dashboard.snapshot_date is None
    assert dashboard.evaluation_date == date(2026, 10, 7)
    assert dashboard.generated_at.isoformat() == "2026-10-07T00:00:00+08:00"


def test_market_data_dates_are_bounded_canonical_and_read_only(tmp_path: Path) -> None:
    db_file = tmp_path / "market.sqlite"
    with sqlite3.connect(db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT);
            CREATE INDEX idx_daily_prices_date ON daily_prices (日期);
            CREATE TABLE market_indices (日期 TEXT, 指數名稱 TEXT);
            CREATE INDEX idx_market_indices_date ON market_indices (日期);
            INSERT INTO daily_prices VALUES
                ('2026-10-05', '2330'), ('20261006', '2330'), ('2026-10-08', '2330');
            INSERT INTO market_indices VALUES
                ('20261006', 'TAIEX'), ('2026-10-08', 'TAIEX'), ('2026-10-07', 'OTHER');
            """
        )
    db_before = db_file.read_bytes()

    service = object.__new__(WorkbenchSourceService)
    service.config = SimpleNamespace(db_file=db_file)
    stock_price_date, market_index_date = service._load_market_data_as_of_dates(
        date(2026, 10, 7)
    )

    assert stock_price_date == date(2026, 10, 6)
    assert market_index_date == date(2026, 10, 6)
    assert db_file.read_bytes() == db_before
    for sidecar in (Path(f"{db_file}-wal"), Path(f"{db_file}-shm")):
        assert not sidecar.exists()


def test_market_data_date_deadline_does_not_return_partial_max(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "market.sqlite"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE daily_prices (日期 TEXT)")
        conn.execute("CREATE INDEX idx_daily_prices_date ON daily_prices (日期)")
        conn.executemany(
            "INSERT INTO daily_prices (日期) VALUES (?)",
            (("2026-10-05",), ("20261006",)),
        )

    readings = iter((0.0, 1.0, 3.0))
    monkeypatch.setattr(
        workbench_source_service_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(readings)),
    )
    with sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        result = workbench_source_service_module._latest_market_table_date(
            conn,
            table_name="daily_prices",
            evaluation_date=date(2026, 10, 7),
        )

    assert result is None


def test_latest_capture_status_exposes_only_safe_timeout_summary(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    producer_now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    capture = create_decision_capture_fixture(
        output_root,
        producer_now=producer_now,
        decision_date="2026-10-06",
        timeout=True,
        private_text="PRIVATE_CAPTURE_PAYLOAD",
    )
    service = object.__new__(WorkbenchSourceService)
    service.config = SimpleNamespace(output_root=output_root)

    status = service._load_latest_capture_status(
        date(2026, 10, 7),
        observed_at=producer_now + timedelta(minutes=1),
    )

    assert status.status == "timeout"
    assert status.run_id == capture.run_id
    assert status.decision_date == date(2026, 10, 6)
    assert status.failure_reason == "snapshot_cli_timeout"
    assert status.snapshot_saved is None
    assert "PRIVATE_CAPTURE_PAYLOAD" not in json.dumps(status.to_dict())


def test_latest_capture_status_rejects_malformed_or_future_records(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    producer_now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    capture = create_decision_capture_fixture(
        output_root,
        producer_now=producer_now,
        decision_date="2026-10-06",
        timeout=True,
    )
    status_path = capture.status_path
    service = object.__new__(WorkbenchSourceService)
    service.config = SimpleNamespace(output_root=output_root)
    original_payload = json.loads(status_path.read_text(encoding="utf-8"))
    observed_at = producer_now + timedelta(minutes=1)

    for key, value in (
        ("task", "other_task"),
        ("status", {"nested": "value"}),
        ("status", ["degraded"]),
        ("decision_date", "2026-10-07T00:00:00"),
        ("decision_date", "2026-10-08"),
    ):
        payload = dict(original_payload)
        payload[key] = value
        status_path.write_text(json.dumps(payload), encoding="utf-8")
        assert service._load_latest_capture_status(
            date(2026, 10, 7),
            observed_at=observed_at,
        ).status == "unknown"

    status_path.write_text("{not-json", encoding="utf-8")
    assert service._load_latest_capture_status(
        date(2026, 10, 7),
        observed_at=observed_at,
    ).status == "unknown"


def test_verified_prelaunch_failure_keeps_unknown_saved_state(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    producer_now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    capture = create_prelaunch_failure_fixture(
        output_root,
        producer_now=producer_now,
        monkeypatch=monkeypatch,
        error_type="FileNotFoundError",
    )
    service = object.__new__(WorkbenchSourceService)
    service.config = SimpleNamespace(output_root=output_root)

    status = service._load_latest_capture_status(
        date(2026, 10, 7), observed_at=producer_now + timedelta(minutes=1),
    )

    assert status.run_id == capture.run_id
    assert status.status == "failed"
    assert status.failure_reason == "snapshot_capture_failed"
    assert status.snapshot_saved is None
