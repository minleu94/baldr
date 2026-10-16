"""回測讀取既有價庫時，不得改寫行情來源。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from sqlite3 import connect
from types import SimpleNamespace

from app_module.backtest_service import BacktestService


def _config(db_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        use_sqlite=True,
        db_file=db_path,
        stock_data_file=db_path.parent / "missing-prices.csv",
        technical_dir=db_path.parent / "missing-technical",
        get_technical_file=lambda stock_code: db_path.parent / f"{stock_code}.csv",
    )


def test_price_and_indicator_reads_preserve_source_database(tmp_path: Path) -> None:
    db_path = tmp_path / "twstock.db"
    with connect(db_path) as connection:
        connection.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" TEXT)'
        )
        connection.execute(
            'CREATE TABLE technical_indicators ("日期" TEXT, "證券代號" TEXT, "MA5" TEXT)'
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES ("20260922", "2330", "123.50")'
        )
        connection.execute(
            'INSERT INTO technical_indicators VALUES ("20260922", "2330", "120.25")'
        )

    before = sha256(db_path.read_bytes()).hexdigest()
    service = BacktestService(_config(db_path))
    prices = service._load_price_data("2330", "2026-09-22", "2026-09-22")
    indicators = service._load_indicator_data("2330", "2026-09-22", "2026-09-22")

    assert prices is not None and len(prices) == 1
    assert prices.iloc[0]["收盤價"] == 123.5
    assert indicators is not None and len(indicators) == 1
    assert indicators.iloc[0]["MA5"] == 120.25
    assert sha256(db_path.read_bytes()).hexdigest() == before
    assert not list(tmp_path.glob("twstock.db-*"))


def test_missing_sqlite_is_not_created_by_backtest_read(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"
    service = BacktestService(_config(db_path))

    assert service._load_price_data("2330", "2026-09-22", "2026-09-22") is None
    assert service._load_indicator_data("2330", "2026-09-22", "2026-09-22") is None
    assert not db_path.exists()
