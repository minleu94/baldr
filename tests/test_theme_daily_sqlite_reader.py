"""只讀明選SQLite版本的價格／法人投影，不寫正式DB。"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from app_module.theme_daily_sqlite_reader import SQLiteThemeMarketReader

DAY = date(2026, 10, 16)
CLOCK = datetime(2026, 10, 18, 12, tzinfo=timezone(timedelta(hours=8)))


def database(tmp_path):
    path = tmp_path / "明選版本.db"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE daily_prices (證券代號 TEXT, 日期 INTEGER, 收盤價 TEXT, 漲跌價差 TEXT, 成交金額 TEXT, 成交股數 TEXT)')
        db.execute('INSERT INTO daily_prices VALUES (?,?,?,?,?,?)', ("2330", 20261016, "110.01", None, "1,234.56", "2000"))
        db.execute('INSERT INTO daily_prices VALUES (?,?,?,?,?,?)', ("9999", 20261016, "999", "999", "999", "999"))
        db.execute('CREATE TABLE institutional_flows (stock_code TEXT, decision_date TEXT, foreign_investor_net TEXT, investment_trust_net TEXT, dealer_net TEXT, observed_at TEXT, available_date TEXT, quality TEXT, source_version TEXT)')
        db.execute('INSERT INTO institutional_flows VALUES (?,?,?,?,?,?,?,?,?)', ("2330", "2026-10-16", "1000", "2000", "-500", "2026-10-17T15:31:00+08:00", "2026-10-17", "degraded", "original"))
    return path


def reader(path, **changes):
    return SQLiteThemeMarketReader(path, expected_sha256=sha256(path.read_bytes()).hexdigest(),
                                   available_at=CLOCK, **changes)


def test_real_sql_integer_dates_precision_units_and_readonly(tmp_path):
    path = database(tmp_path)
    before = path.read_bytes()
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert path.read_bytes() == before
    assert len(result.prices) == len(result.flows) == 1
    price = result.prices[0]
    assert price.stock_id == "2330" and price.data_date == DAY
    assert price.close_twd == Decimal("110.01") and price.change_twd is None
    assert price.turnover_twd == Decimal("1234.56") and price.volume_shares == 2000
    assert result.flows[0].net_shares == 2500
    assert result.flows[0].net_turnover_twd is None
    assert "institutional_quality:degraded" in result.warnings
    assert not Path(str(path) + "-wal").exists()


def test_missing_component_does_not_turn_partial_institutional_total_into_full(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE institutional_flows SET dealer_net=NULL')
    assert reader(path).read(("2330",), DAY, CLOCK).flows[0].net_shares is None


def test_unknown_direction_and_fractional_shares_remain_missing(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE daily_prices SET 漲跌價差="--", 成交股數="1.5"')
    price = reader(path).read(("2330",), DAY, CLOCK).prices[0]
    assert price.change_twd is None and price.volume_shares is None


def test_positive_magnitude_without_direction_does_not_become_gain(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE daily_prices SET 漲跌價差="2.5"')
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert result.prices[0].change_twd is None
    assert "missing_change_direction" in result.warnings
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE daily_prices ADD COLUMN "漲跌(+/-)" TEXT')
        db.execute('UPDATE daily_prices SET "漲跌(+/-)"="-"')
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert result.prices[0].change_twd == Decimal("-2.5")


def test_hash_mismatch_or_sidecar_refuses_live_source(tmp_path):
    path = database(tmp_path)
    source = reader(path)
    with path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="SHA256"):
        source.read(("2330",), DAY, CLOCK)
    source = reader(path)
    Path(str(path) + "-wal").touch()
    with pytest.raises(ValueError, match="旁檔"):
        source.read(("2330",), DAY, CLOCK)


def test_no_read_before_successful_saved_hour(tmp_path):
    path = database(tmp_path)
    result = reader(path).read(("2330",), DAY, CLOCK - timedelta(microseconds=1))
    assert result.prices == result.flows == ()


def test_missing_optional_columns_do_not_invent_values_or_flow_table(tmp_path):
    path = tmp_path / "minimal.db"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE daily_prices (證券代號 TEXT, 日期 TEXT)')
        db.execute('INSERT INTO daily_prices VALUES (?,?)', ("2330", "2026-10-16"))
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert result.prices[0].close_twd is None
    assert result.prices[0].turnover_twd is None and result.flows == ()
    assert "institutional_flows_schema_unavailable" in result.warnings


def test_future_row_clock_cannot_be_hidden_by_older_db_clock(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE institutional_flows SET observed_at="2026-10-19T15:45:00+08:00"')
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert result.flows[0].available_at > CLOCK
    assert result.flows[0].available_at.minute == 0


def test_source_clock_converts_to_taipei_before_rounding(tmp_path):
    path = database(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE institutional_flows SET observed_at="2026-10-19T10:31:00+05:30"')
    result = reader(path).read(("2330",), DAY, CLOCK)
    assert result.flows[0].available_at == datetime(2026, 10, 19, 14, tzinfo=CLOCK.tzinfo)


def test_missing_file_does_not_create_database(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        SQLiteThemeMarketReader(path, expected_sha256="0" * 64, available_at=CLOCK)
    assert not path.exists()
