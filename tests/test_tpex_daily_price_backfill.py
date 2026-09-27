import sqlite3

import pytest

import data_module.tpex_daily_price_backfill as backfill_module

from data_module.tpex_daily_price_backfill import (
    TpexDailyPriceDiagnostic,
    _insert_daily_price_rows,
    apply_tpex_daily_price_backfill,
    build_tpex_daily_price_plan,
    normalize_tpex_daily_price_rows,
)


def test_normalize_tpex_daily_price_rows_maps_quote_fields():
    result = normalize_tpex_daily_price_rows(
        [
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "42.50",
                "Open": "42.00",
                "High": "43.00",
                "Low": "41.50",
                "TradingShares": "1,234,000",
                "TransactionAmount": "52,445,000",
                "TransactionNumber": "901",
                "Change": "+0.50",
                "LastBestBidPrice": "42.45",
                "LastBestBidVolume": "3",
                "LastBestAskPrice": "42.50",
                "LastBestAskVolume": "2",
                "PERatio": "12.34",
            }
        ],
        fallback_date="2026-06-16",
    )

    assert result.diagnostics == ()
    assert result.rows == (
        {
            "日期": "20260616",
            "證券代號": "3207",
            "證券名稱": "耀勝",
            "成交股數": 1234000,
            "成交筆數": 901,
            "成交金額": 52445000,
            "開盤價": "42.00",
            "最高價": "43.00",
            "最低價": "41.50",
            "收盤價": "42.50",
            "漲跌": "+",
            "漲跌價差": "0.50",
            "最後揭示買價": "42.45",
            "最後揭示買量": 3,
            "最後揭示賣價": "42.50",
            "最後揭示賣量": 2,
            "本益比": "12.34",
        },
    )


@pytest.mark.parametrize(
    ("missing_source_field", "output_column"),
    [("Open", "開盤價"), ("High", "最高價"), ("Low", "最低價")],
)
def test_normalize_tpex_daily_price_rows_preserves_missing_ohlc(
    missing_source_field, output_column
):
    source_row = {
        "Date": "1150616",
        "SecuritiesCompanyCode": "3207",
        "CompanyName": "耀勝",
        "Close": "42.50",
        "Open": "42.00",
        "High": "43.00",
        "Low": "41.50",
    }
    source_row.pop(missing_source_field)

    result = normalize_tpex_daily_price_rows(
        [source_row],
        fallback_date="2026-06-16",
    )

    assert result.diagnostics == ()
    assert len(result.rows) == 1
    assert result.rows[0][output_column] is None
    assert result.rows[0]["收盤價"] == "42.50"


def test_normalize_tpex_daily_price_rows_reports_invalid_price():
    result = normalize_tpex_daily_price_rows(
        [
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "--",
            }
        ],
        fallback_date="2026-06-16",
    )

    assert result.rows == ()
    diagnostic = result.diagnostics[0]
    assert isinstance(diagnostic, TpexDailyPriceDiagnostic)
    payload = diagnostic.to_dict()
    assert tuple(payload) == ("code", "factor_name", "stock_code", "message")
    assert payload == {
        "code": "tpex_daily_price.invalid_price",
        "factor_name": "market_data.tpex_daily_price",
        "stock_code": "3207",
        "message": "TPEX daily price row has missing or non-positive close price",
    }


def test_normalize_tpex_daily_price_rows_reports_invalid_stock_code() -> None:
    result = normalize_tpex_daily_price_rows(
        [
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "00720B",
                "CompanyName": "債券",
                "Close": "100.00",
            }
        ],
        fallback_date="2026-06-16",
    )

    assert result.rows == ()
    diagnostic = result.diagnostics[0]
    assert isinstance(diagnostic, TpexDailyPriceDiagnostic)
    payload = diagnostic.to_dict()
    assert tuple(payload) == ("code", "factor_name", "stock_code", "message")
    assert payload == {
        "code": "tpex_daily_price.invalid_stock_code",
        "factor_name": "market_data.tpex_daily_price",
        "stock_code": "00720B",
        "message": "TPEX daily price row is missing a four-digit stock code",
    }


def test_normalize_tpex_daily_price_rows_preserves_diagnostic_order() -> None:
    result = normalize_tpex_daily_price_rows(
        [
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "00720B",
                "CompanyName": "債券",
                "Close": "100.00",
            },
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "--",
            },
        ],
        fallback_date="2026-06-16",
    )

    assert result.rows == ()
    assert [item.code for item in result.diagnostics] == [
        "tpex_daily_price.invalid_stock_code",
        "tpex_daily_price.invalid_price",
    ]


def test_build_tpex_daily_price_plan_skips_existing_rows(tmp_path):
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )
        conn.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "收盤價") VALUES ("20260616", "3207", 40.0)'
        )

    result = build_tpex_daily_price_plan(
        db_file=db_file,
        source_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "42.50",
            }
        ],
        fallback_date="2026-06-16",
    )

    assert result.ready_for_apply is False
    assert result.existing_count == 1
    assert result.insert_count == 0


def test_build_tpex_daily_price_plan_filters_to_requested_date(tmp_path):
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )

    result = build_tpex_daily_price_plan(
        db_file=db_file,
        source_rows=[
            {
                "Date": "1150615",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "41.50",
            },
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "42.50",
            },
        ],
        fallback_date="2026-06-16",
    )

    assert result.insert_count == 1
    assert result.rows[0]["日期"] == "20260616"


def test_build_tpex_daily_price_plan_non_strict_skips_non_common_and_invalid_rows(tmp_path):
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )

    result = build_tpex_daily_price_plan(
        db_file=db_file,
        source_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "00720B",
                "CompanyName": "債券",
                "Close": "100.00",
            },
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "2948",
                "CompanyName": "停牌股",
                "Close": "--",
            },
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "42.50",
            },
        ],
        fallback_date="2026-06-16",
        strict=False,
    )

    assert result.diagnostics == ()
    assert result.insert_count == 1
    assert result.rows[0]["證券代號"] == "3207"


def test_apply_tpex_daily_price_backfill_inserts_rows_and_backs_up(tmp_path):
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "backup"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )

    result = apply_tpex_daily_price_backfill(
        db_file=db_file,
        backup_dir=backup_dir,
        source_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "耀勝",
                "Close": "42.50",
            }
        ],
        fallback_date="2026-06-16",
    )

    assert result.applied is True
    assert result.backup_file is not None
    assert result.backup_file.exists()
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute('SELECT "證券代號", "日期", "收盤價" FROM daily_prices').fetchall()
    assert rows == [("3207", "20260616", 42.5)]


def test_insert_only_does_not_overwrite_existing_row(tmp_path):
    db_file = tmp_path / "twstock.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )
        conn.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "收盤價") VALUES (?, ?, ?)',
            ("20260616", "3207", 40.0),
        )

    inserted_count = _insert_daily_price_rows(
        db_file,
        (
            {
                "日期": "20260616",
                "證券代號": "3207",
                "收盤價": "42.50",
            },
        ),
        insert_only=True,
    )

    assert inserted_count == 0
    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            'SELECT "收盤價" FROM daily_prices WHERE "證券代號" = ? AND "日期" = ?',
            ("3207", "20260616"),
        ).fetchone() == (40.0,)


def test_apply_insert_only_keeps_row_added_after_preflight(tmp_path, monkeypatch):
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "backup"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )

    original_backup = backfill_module._backup_db

    def backup_then_insert(path, destination):
        backup_file = original_backup(path, destination)
        with sqlite3.connect(path) as conn:
            conn.execute(
                'INSERT INTO daily_prices ("日期", "證券代號", "證券名稱", "收盤價") VALUES (?, ?, ?, ?)',
                ("20260616", "3207", "既有列", 40.0),
            )
        return backup_file

    monkeypatch.setattr(backfill_module, "_backup_db", backup_then_insert)
    result = apply_tpex_daily_price_backfill(
        db_file=db_file,
        backup_dir=backup_dir,
        source_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyName": "新列",
                "Close": "42.50",
            }
        ],
        fallback_date="2026-06-16",
        insert_only=True,
    )

    assert result.applied is True
    assert result.inserted_count == 0
    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            'SELECT "證券名稱", "收盤價" FROM daily_prices WHERE "證券代號" = ? AND "日期" = ?',
            ("3207", "20260616"),
        ).fetchone() == ("既有列", 40.0)
