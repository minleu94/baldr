"""隔離SQLite→有界發布→已核驗個股consumer的實際閉環。"""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import os
import sqlite3

import pytest

from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.stock_research_report_service import StockResearchReportReadService


def _seed(tmp_path: Path) -> tuple[Path, date]:
    db = tmp_path / "source.db"
    dates = [date(2026, 7, 1) + timedelta(days=offset) for offset in range(65)]
    with sqlite3.connect(db) as connection:
        connection.executescript('''
            CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT,
                最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER);
            CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, MA20 TEXT, MA60 TEXT);
        ''')
        for code in ("2382", "1477"):
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", [
                (day.isoformat(), code, "100", "105", "95", "101", 1000) for day in dates
            ])
            connection.execute("INSERT INTO technical_indicators VALUES (?,?,?,?)", (dates[-1].isoformat(), code, "99", "102"))
    # 受控每日日期不冒稱官方交易日曆；snapshot的calendar completeness須維持unknown。
    return db, dates[-1]


def _consumer(db: Path, day: date, root: Path, cohort: str = "controlled-two"):
    return StockResearchReportReadService(
        SimpleNamespace(db_file=db, output_root=None),
        clock=lambda: datetime.combine(day + timedelta(days=1), time(12), tzinfo=ZoneInfo("Asia/Taipei")),
        daily_market_snapshot_root=root, daily_market_snapshot_cohort_id=cohort,
    )


def test_readonly_source_schema_and_revision_guards(tmp_path):
    db, day = _seed(tmp_path)
    with SQLiteDailyMarketSnapshotSource(db, day) as source:
        first = source.load("2382")
        assert len(first[0]) == 65
        assert first[2].endswith("stock:2382")
        assert first[3]["schema_identity_sha256"]
        assert source.load("2382") == first
        stat = db.stat()
        os.utime(db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        with pytest.raises(ValueError, match="source_changed"):
            source.validate_source_stable()
    bad = tmp_path / "bad.db"
    with sqlite3.connect(bad) as connection:
        connection.execute("CREATE TABLE daily_prices (日期 TEXT)")
    with pytest.raises(ValueError, match="schema_incompatible"):
        with SQLiteDailyMarketSnapshotSource(bad, day):
            pass


def test_explicit_snapshot_settings_must_be_paired(tmp_path):
    db, _day = _seed(tmp_path)
    with pytest.raises(ValueError, match="cohort_id"):
        StockResearchReportReadService(SimpleNamespace(db_file=db, output_root=None), daily_market_snapshot_root=tmp_path / "snapshots")


def test_cli_rejects_output_outside_isolation_before_source_read(tmp_path, capsys):
    from scripts.produce_daily_market_research_snapshot import main
    outside = Path(__file__).resolve().parents[1] / ".tmp_ux19_forbidden_output"
    rc = main(["--db-path", str(tmp_path / "missing.db"), "--output-root", str(outside),
               "--cohort-id", "controlled", "--decision-cutoff", "2026-09-01T16:00:00+08:00", "--symbols", "2382"])
    assert rc == 2
    assert "output_root" in capsys.readouterr().out
    assert not outside.exists()


def _produce(db: Path, day: date, root: Path):
    cutoff = datetime.combine(day, time(16), tzinfo=ZoneInfo("Asia/Taipei"))
    with SQLiteDailyMarketSnapshotSource(db, day) as source:
        def load_inputs(code, requested_day):
            assert requested_day == day
            points, technical, scope, refs = source.load(code)
            return DailyMarketSnapshotInput(code, scope, points, technical, refs)
        result = DailyMarketSnapshotProducer(root).produce(
            cohort_id="controlled-two", decision_cutoff=cutoff, stock_codes=("2382", "1477"),
            source_loader=load_inputs, before_publish=source.validate_source_stable,
        )
        assert result.published or result.status == "unchanged", result.to_dict()
        return result


def test_real_consumer_uses_verified_publication_and_rejects_stale_source(tmp_path, monkeypatch):
    db, day = _seed(tmp_path)
    root = tmp_path / "snapshots"
    _produce(db, day, root)
    service = _consumer(db, day, root)
    def must_not_project(**_kwargs):
        raise AssertionError("已發布consumer不得改走live projector")
    monkeypatch.setattr(service.daily_market_feature_snapshot_service, "project", must_not_project)
    first = service.read_report("2382", as_of_date=day)
    assert first.shared_daily_features["readback"]["mode"] == "verified_published_research_snapshot"
    assert first.shared_daily_features["policy"]["historical_pit_eligible"] is False
    assert first.shared_daily_features["policy"]["market_calendar_completeness"] == "unknown"
    assert first.shared_daily_features["conditions"]["close_above_ma20"]["state"] == "match"
    assert any("收盤 101 高於 MA20 99" in reason for reason in first.rule_reasons)
    old_identity = first.shared_daily_features["snapshot_identity_sha256"]

    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE daily_prices SET 收盤價='103' WHERE 日期=? AND 證券代號='2382'", (day.isoformat(),))
    stale = service.read_report("2382", as_of_date=day)
    assert stale.shared_daily_features["projection_status"] == "failed"
    assert stale.shared_daily_features["conditions"]["close_above_ma20"]["state"] == "unknown"
    assert "readback" not in stale.shared_daily_features
    _produce(db, day, root)
    revised = service.read_report("2382", as_of_date=day)
    assert revised.shared_daily_features["snapshot_identity_sha256"] != old_identity
    assert revised.shared_daily_features["readback"]["mode"] == "verified_published_research_snapshot"
    wrong_cohort = _consumer(db, day, root, cohort="different-cohort").read_report("2382", as_of_date=day)
    assert wrong_cohort.shared_daily_features["projection_status"] == "failed"
    wrong_date = service.read_report("2382", as_of_date=day - timedelta(days=1))
    assert wrong_date.shared_daily_features["projection_status"] == "failed"
