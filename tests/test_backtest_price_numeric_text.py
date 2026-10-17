"""回測來源合法千分位不可變缺件；原檔與整數股數必須保留。"""
import csv
from decimal import Decimal
from hashlib import sha256
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService


def source_case(tmp_path, source):
    fields = ["日期", "證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數"]
    rows = [("20250102", "2330", "1,040.00", "1,050.00", "1,035.00", "1,045.00", "9,007,199,254,740,993"),
            ("20250103", "2330", "--", "--", "--", "--", "0")]
    path = tmp_path / ("prices.db" if source == "sqlite" else "prices.csv")
    if source == "sqlite":
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE daily_prices (' + ','.join('"' + key + '" TEXT' for key in fields) + ')')
            connection.executemany('INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)', rows)
    else:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)
    config = SimpleNamespace(use_sqlite=source == "sqlite", db_file=path, stock_data_file=path)
    return path, BacktestService(config)


@pytest.mark.parametrize("source", ["sqlite", "csv"])
def test_legitimate_thousands_remain_original_values(tmp_path, source):
    path, service = source_case(tmp_path, source)
    before = sha256(path.read_bytes()).hexdigest()
    frame = service._load_price_data("2330", "2025-01-02", "2025-01-03")
    assert Decimal(str(frame.iloc[0]["收盤價"])) == Decimal("1045.00")
    assert Decimal(str(frame.iloc[0]["成交股數"])) == Decimal("9007199254740993")
    assert sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("source", ["sqlite", "csv"])
def test_genuine_missing_remains_unavailable_and_parser_revision_is_named(tmp_path, source):
    _, service = source_case(tmp_path, source)
    frame = service._load_price_data("2330", "2025-01-02", "2025-01-03")
    assert pd.isna(frame.iloc[1]["收盤價"])
    assert frame.attrs["price_input_preparation"] == "historical-price-numeric-text.v1"


@pytest.mark.parametrize("coerce", [True, False])
def test_missing_quantity_cannot_round_other_rows_or_repair_invalid_grouping(coerce):
    raw = pd.DataFrame({"收盤價": ["1,045.00", "10,45.00"],
                        "成交股數": ["9,007,199,254,740,993", "--"]})
    parsed = BacktestService._prepare_price_text(raw, coerce_numeric=coerce)
    assert Decimal(str(parsed.iloc[0]["成交股數"])) == Decimal("9007199254740993")
    assert pd.isna(parsed.iloc[1]["成交股數"])
    if coerce:
        assert pd.isna(parsed.iloc[1]["收盤價"])
    else:
        assert parsed.iloc[1]["收盤價"] == "10,45.00"
    assert raw.iloc[0]["收盤價"] == "1,045.00" and raw.iloc[1]["成交股數"] == "--"
