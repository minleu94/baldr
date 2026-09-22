"""9/21 價格跨日稽核器的隔離回歸測試。"""

from __future__ import annotations

import sqlite3

from scripts.audit_price_jump_20260921 import _cross_source, _load_csv_rows, _load_sqlite_rows


def test_csv_filename_supplies_date_when_twse_row_has_no_date(tmp_path) -> None:
    path = tmp_path / "20260921.csv"
    path.write_text(
        "證券代號,開盤價,最高價,最低價,收盤價,成交股數,成交金額,漲跌(+/-),漲跌價差\n"
        "2330,100,102,99,101,1000,100500,+,1\n",
        encoding="utf-8-sig",
    )

    rows = _load_csv_rows(path, source="twse_raw", fallback_date="20260921")

    assert len(rows) == 1
    assert rows[0]["日期"] == "20260921"
    assert rows[0]["證券代號"] == "2330"


def test_csv_sign_fallback_keeps_all_sign_columns(tmp_path) -> None:
    path = tmp_path / "20260921.csv"
    path.write_text(
        "日期,證券代號,開盤價,最高價,最低價,收盤價,成交股數,成交金額,漲跌(+/-),漲跌,漲跌價差\n"
        "20260921,1256,170,171.5,170,170,100,17000,,-,2\n",
        encoding="utf-8-sig",
    )

    rows = _load_csv_rows(path, source="twse_raw")

    assert rows[0]["漲跌"] == "-"
    assert rows[0]["_sign_candidates"] == {"漲跌(+/-)": "", "漲跌": "-"}


def test_sqlite_date_filter_accepts_numeric_and_iso_dates() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE daily_prices (
            日期 TEXT, 證券代號 TEXT, 開盤價 REAL, 最高價 REAL, 最低價 REAL,
            收盤價 REAL, 成交股數 INTEGER, 成交金額 INTEGER, 漲跌價差 REAL,
            [漲跌(+/-)] TEXT
        )
        """
    )
    rows = [
        ("2026-09-18", "1256", 172, 172, 170, 172, 100, 17100, 1, "+"),
        ("20260921", "1256", 170, 171, 170, 170, 100, 17000, 2, "-"),
    ]
    connection.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    result = _load_sqlite_rows(connection, "20260918", "20260921")

    assert [row["日期"] for row in result] == ["20260918", "20260921"]
    connection.close()


def test_cross_source_without_execution_is_not_reported_as_missing() -> None:
    result = _cross_source(
        [{"日期": "20260921", "證券代號": "1256"}],
        [],
        "merged",
        executed=False,
    )

    assert result["status"] == "not_run"
    assert result["included"] is False
    assert result["executed"] is False
    assert result["missing_in_source_count"] is None


def test_cross_source_executed_empty_source_is_missing() -> None:
    result = _cross_source(
        [{"日期": "20260921", "證券代號": "1256"}],
        [],
        "raw",
        executed=True,
    )

    assert result["status"] == "source_missing_or_empty"
    assert result["included"] is False
    assert result["executed"] is True
    assert result["missing_in_source_count"] is None
