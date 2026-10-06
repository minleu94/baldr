"""現況快照的單位、版本冪等與歷史隔離。"""
import csv
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import pytest
from types import SimpleNamespace

from app_module.stock_research_report_service import StockResearchReportReadService
from data_module.current_fundamental_snapshots import insert_observations, monthly_snapshot_rows


def test_snapshot_money_units_idempotency_and_date_only_isolation(tmp_path: Path) -> None:
    path = tmp_path / "monthly.csv"
    source = dict(stock_code="2330", period="2026-07", fetched_at="2026-09-01T01:00:00+00:00",
                  current_month_revenue="123,456", source_version="official-hash-1", market="twse", source="mops")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source))
        writer.writeheader()
        writer.writerow(source)
    records = monthly_snapshot_rows(path)
    assert records[0]["value"] == "123456000"
    assert records[0]["period_basis"] == "unknown"
    assert records[0]["basis_verified"] == "0"
    assert records[0]["aggregate_feature_eligible"] == "0"
    database = tmp_path / "test.db"
    connection = sqlite3.connect(database)
    assert insert_observations(connection, records) == 1
    assert insert_observations(connection, records) == 0
    # 未來觀測不可見，即使報告 period 比現在早。
    future = dict(records[0], period="2026-08", observed_at="2099-01-01T00:00:00+00:00")
    insert_observations(connection, [future])
    connection.commit()
    connection.close()
    service = StockResearchReportReadService(SimpleNamespace(db_file=database), clock=lambda: datetime.now(timezone.utc))
    current = service.read_report("2330")
    assert [(x.period, str(x.value), x.unit) for x in current.fundamentals] == [("2026-07", "123456000", "TWD")]
    historical = service.read_report("2330", as_of_date=datetime.now(timezone.utc).date())
    assert not historical.fundamentals


def test_ownership_snapshot_timestamp_does_not_grant_date_only_pit(tmp_path: Path) -> None:
    database = tmp_path / "ownership.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE tdcc_shareholding (stock_code TEXT, decision_date TEXT, available_date TEXT, observed_at TEXT, large_holder_ratio_bp INTEGER)")
    connection.execute("INSERT INTO tdcc_shareholding VALUES ('2330','2026-09-04','2026-09-10','2026-09-09T05:00:00+00:00',7000)")
    connection.commit()
    connection.close()
    config = SimpleNamespace(db_file=database)
    before = StockResearchReportReadService(config, clock=lambda: datetime(2026, 9, 9, 4, tzinfo=timezone.utc))
    after = StockResearchReportReadService(config, clock=lambda: datetime(2026, 9, 9, 6, tzinfo=timezone.utc))
    assert not before.read_report("2330").shareholding
    assert after.read_report("2330").shareholding[0].value == 7000
    assert after.read_report("2330").shareholding[0].available_at == "2026-09-09T05:00:00+00:00"
    assert not after.read_report("2330", as_of_date="2026-09-09").shareholding


def test_monthly_rejects_future_period_with_past_capture(tmp_path: Path) -> None:
    path = tmp_path / "future.csv"
    path.write_text("stock_code,period,fetched_at\n2330,2099-01,2026-09-01T01:00:00+00:00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="period ends after observation"):
        monthly_snapshot_rows(path)


def test_legacy_current_table_upgrades_additively_with_unknown_defaults(tmp_path: Path) -> None:
    path = tmp_path / "monthly.csv"
    source = dict(stock_code="2330", period="2026-07", fetched_at="2026-09-01T01:00:00+00:00",
                  current_month_revenue="123,456", source_version="official-hash-1", market="twse", source="mops")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source))
        writer.writeheader()
        writer.writerow(source)
    record = monthly_snapshot_rows(path)[0]

    connection = sqlite3.connect(tmp_path / "legacy.db")
    connection.execute(
        """CREATE TABLE fundamental_current_observations (
        stock_code TEXT NOT NULL, kind TEXT NOT NULL, period TEXT NOT NULL,
        as_of_date TEXT NOT NULL, item_code TEXT NOT NULL, item_name TEXT NOT NULL,
        value TEXT NOT NULL, unit TEXT NOT NULL, observed_at TEXT NOT NULL,
        source TEXT NOT NULL, source_version TEXT NOT NULL, market TEXT NOT NULL,
        PRIMARY KEY(stock_code, kind, period, item_code, source_version))"""
    )
    connection.execute(
        "INSERT INTO fundamental_current_observations VALUES "
        "('1101','monthly_revenue','2026-06','2026-06-30','revenue','月營收','456','TWD',"
        "'2026-07-10T00:00:00+00:00','mops','old-hash','twse')"
    )
    assert insert_observations(connection, [record]) == 1
    legacy = connection.execute(
        "SELECT value, period_basis, basis_verified, aggregate_feature_eligible "
        "FROM fundamental_current_observations WHERE stock_code='1101'"
    ).fetchone()
    current = connection.execute(
        "SELECT value, period_basis, basis_verified, aggregate_feature_eligible "
        "FROM fundamental_current_observations WHERE stock_code='2330'"
    ).fetchone()
    assert legacy == ("456", "unknown", 0, 0)
    assert current == ("123456000", "unknown", 0, 0)
    connection.close()


def test_verified_basis_requires_a_recognized_source_hash(tmp_path: Path) -> None:
    path = tmp_path / "monthly.csv"
    source = dict(stock_code="2330", period="2026-07", fetched_at="2026-09-01T01:00:00+00:00",
                  current_month_revenue="123,456", source_version="official-hash-1", market="twse", source="mops")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source))
        writer.writeheader()
        writer.writerow(source)
    forged = dict(
        monthly_snapshot_rows(path)[0],
        period_basis="monthly_flow",
        basis_verified="1",
        aggregate_feature_eligible="1",
    )
    connection = sqlite3.connect(tmp_path / "invalid.db")
    with pytest.raises(ValueError, match="recognized, hashed MOPS source|matching official HTML hash"):
        insert_observations(connection, [forged])
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fundamental_current_observations'"
    ).fetchone() is None
    connection.close()
