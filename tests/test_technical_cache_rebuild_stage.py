from __future__ import annotations

from datetime import date, timedelta
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from analysis_module.technical_analysis.technical_indicators import (
    CAUSAL_INDICATOR_COLUMNS,
)
from scripts.technical_cache_rebuild_stage import (
    COMPUTED_TABLE,
    REBUILD_COLUMNS,
    stage_rebuild,
)


def _create_source_db(path: Path, *, duplicate_daily_key: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique_clause = "" if duplicate_daily_key else ", UNIQUE (日期, 證券代號)"
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"""CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                成交股數 INTEGER,
                成交筆數 INTEGER,
                成交金額 INTEGER,
                開盤價 REAL,
                最高價 REAL,
                最低價 REAL,
                收盤價 REAL,
                漲跌 TEXT,
                漲跌價差 REAL,
                最後揭示買價 REAL,
                最後揭示買量 INTEGER,
                最後揭示賣價 REAL,
                最後揭示賣量 INTEGER,
                本益比 REAL
                {unique_clause}
            )"""
        )
        connection.execute(
            "CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, RSI REAL)"
        )
        connection.executemany(
            "INSERT INTO technical_indicators VALUES (?, ?, ?)",
            [("20230101", "9999", 10.0), ("20230101", "00720B", 20.0)],
        )
        rows = []
        start = date(2024, 1, 1)
        for index in range(65):
            close = 50.0 + index
            missing_ohlc = index == 40
            rows.append(
                (
                    (start + timedelta(days=index)).strftime("%Y%m%d"),
                    "2330",
                    "台積電",
                    1000 + index,
                    100 + index,
                    50000 + index,
                    None if missing_ohlc else close - 0.5,
                    None if missing_ohlc else close + 1.0,
                    None if missing_ohlc else close - 1.0,
                    close,
                    "+",
                    0.5,
                    close - 0.1,
                    2,
                    close + 0.1,
                    3,
                    20.0,
                )
            )
        for index in range(8):
            close = 20.0 + index
            rows.append(
                (
                    (start + timedelta(days=index)).strftime("%Y%m%d"),
                    "1234",
                    "測試短序列",
                    0,
                    0,
                    0,
                    close,
                    close + 1,
                    close - 1,
                    close,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
        for index in range(2):
            close = 100.0 + index
            rows.append(
                (
                    (start + timedelta(days=index)).strftime("%Y%m%d"),
                    "0050",
                    "元大台灣50",
                    100,
                    10,
                    10000,
                    close,
                    close + 1,
                    close - 1,
                    close,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
        close = 30.0
        rows.append(
            (
                "20240101",
                "00720B",
                "測試債券ETF",
                10,
                1,
                300,
                close,
                close + 1,
                close - 1,
                close,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        )
        if duplicate_daily_key:
            rows.append(rows[0])
        connection.executemany(
            "INSERT INTO daily_prices VALUES (" + ",".join("?" for _ in range(17)) + ")",
            rows,
        )


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture
def stage_inputs(tmp_path: Path):
    source_db = tmp_path / "receipt" / "source.sqlite"
    formal_root = tmp_path / "formal"
    technical_dir = formal_root / "technical_analysis"
    meta_dir = formal_root / "meta_data"
    technical_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    _create_source_db(source_db)

    stock_fields = [
        "日期",
        "證券代號",
        "RSI",
        "Legacy",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "成交股數",
        "ATR",
    ]
    gap_day = (date(2024, 1, 1) + timedelta(days=40)).strftime("%Y%m%d")
    _write_csv(
        technical_dir / "2330_indicators.csv",
        stock_fields,
        [
            {
                "日期": "20240101",
                "證券代號": "2330",
                "RSI": "999",
                "Legacy": "keep-source-value",
                "開盤價": "999",
                "最高價": "999",
                "最低價": "999",
                "收盤價": "999",
                "成交股數": "999",
                "ATR": "999",
            },
            {
                "日期": gap_day,
                "證券代號": "2330",
                "RSI": "999",
                "Legacy": "keep-gap-value",
                "開盤價": "999",
                "最高價": "999",
                "最低價": "999",
                "收盤價": "999",
                "成交股數": "999",
                "ATR": "999",
            },
            {
                "日期": "20200101",
                "證券代號": "2330",
                "RSI": "77",
                "Legacy": "no-source",
                "開盤價": "7",
                "最高價": "8",
                "最低價": "6",
                "收盤價": "7",
                "成交股數": "70",
                "ATR": "7",
            },
        ],
    )
    aggregate_path = meta_dir / "all_stocks_data.csv"
    _write_csv(
        aggregate_path,
        ["日期", "證券代號", "Legacy", "RSI"],
        [
            {"日期": "20240101", "證券代號": "2330", "Legacy": "keep", "RSI": "999"},
            {"日期": "20200101", "證券代號": "9999", "Legacy": "no-source", "RSI": "88"},
        ],
    )
    return source_db, formal_root, technical_dir, aggregate_path


def test_stage_rebuild_streams_outputs_and_preserves_formal_inputs(stage_inputs, tmp_path):
    source_db, formal_root, technical_dir, aggregate_path = stage_inputs
    before_source = _sha256(source_db)
    formal_before = {
        path: _sha256(path)
        for path in [technical_dir / "2330_indicators.csv", aggregate_path]
    }
    output_dir = tmp_path / "stage"

    manifest = stage_rebuild(source_db, formal_root, output_dir)

    assert manifest["source_db"] == str(source_db.resolve())
    assert manifest["source_sha256"] == before_source
    assert manifest["computed_table"] == COMPUTED_TABLE
    assert manifest["computed_sha256"] == _sha256(output_dir / "computed.sqlite")
    assert manifest["rows"] == 65 + 8 + 2 + 1
    assert {"2330", "1234", "0050", "00720B", "9999"} <= set(manifest["symbols"])
    assert manifest["target_symbol_scope"] == (
        "all existing daily_prices symbols union existing technical_indicators symbols"
    )
    assert manifest["symbols_without_source"] == ["9999"]
    assert all(_sha256(path) == digest for path, digest in formal_before.items())
    assert _sha256(source_db) == before_source

    with sqlite3.connect(output_dir / "computed.sqlite") as connection:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{COMPUTED_TABLE}")')]
        assert set(CAUSAL_INDICATOR_COLUMNS) <= set(columns)
        assert set(("日期", "證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數")) <= set(columns)
        values = connection.execute(
            f'SELECT "日期", "證券代號", "MA5", "ATR", "開盤價", "成交股數" FROM "{COMPUTED_TABLE}" WHERE "證券代號"=? ORDER BY "日期"',
            ("2330",),
        ).fetchall()
        assert values[0][0] == "20240101"
        assert values[0][1] == "2330"
        assert values[0][2] is None  # warmup is not filled from old CSV data
        assert values[40][2] is None  # missing OHLC row is a causal gap
        assert values[-1][2] is not None
        assert values[-1][3] is not None
        short_values = connection.execute(
            f'SELECT "MA5", "MACD" FROM "{COMPUTED_TABLE}" WHERE "證券代號"=? ORDER BY "日期"',
            ("1234",),
        ).fetchall()
        assert len(short_values) == 8
        assert all(row[0] is None for row in short_values[:4])
        assert all(row[0] is not None for row in short_values[4:])
        assert all(row[1] is None for row in short_values)

    stock_path = output_dir / "staged" / "technical_analysis" / "2330_indicators.csv"
    stock_rows = {row["日期"]: row for row in _read_csv(stock_path)}
    assert stock_rows["20240101"]["Legacy"] == "keep-source-value"
    assert stock_rows["20200101"]["RSI"] == "77"
    assert stock_rows["20200101"]["Legacy"] == "no-source"
    gap_day = (date(2024, 1, 1) + timedelta(days=40)).strftime("%Y%m%d")
    assert stock_rows[gap_day]["ATR"] == ""
    assert stock_rows[gap_day]["開盤價"] == ""
    assert stock_rows["20240102"]["收盤價"] == "51.0"
    assert all(name in stock_rows["20240101"] for name in REBUILD_COLUMNS)
    assert any(file["before_sha256"] is None for file in manifest["files"])

    aggregate_rows = _read_csv(output_dir / "staged" / "meta_data" / "all_stocks_data.csv")
    aggregate_keys = {(row["日期"], row["證券代號"]) for row in aggregate_rows}
    assert ("20200101", "9999") in aggregate_keys
    assert len(aggregate_rows) == manifest["rows"] + 1
    ordered_keys = [
        (row["日期"].replace("-", "").replace("/", ""), row["證券代號"])
        for row in aggregate_rows
    ]
    assert ordered_keys == sorted(ordered_keys)
    assert next(
        row for row in aggregate_rows
        if row["日期"] == "20240101" and row["證券代號"] == "2330"
    )["Legacy"] == "keep"
    assert aggregate_rows[-1]["日期"] == "20240305"
    assert "ADX" in aggregate_rows[0] and "ATR" in aggregate_rows[0]
    assert manifest["preserved_existing_no_source_keys"]["aggregate_csv_rows"] == 1
    assert manifest["preserved_existing_no_source_keys"]["per_stock_csv_rows"] == 1
    assert all(
        file["target_path"] and file["staged_path"] and file["after_sha256"]
        for file in manifest["files"]
    )
    assert all(Path(file["staged_path"]).is_file() for file in manifest["files"])
    assert json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")) == manifest

    short_rows = _read_csv(
        output_dir / "staged" / "technical_analysis" / "1234_indicators.csv"
    )
    assert [row["日期"] for row in short_rows] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-06",
        "2024-01-07",
        "2024-01-08",
    ]


def test_new_stock_csv_rows_follow_existing_date_style(stage_inputs, tmp_path):
    source_db, formal_root, technical_dir, _aggregate_path = stage_inputs
    _write_csv(
        technical_dir / "0050_indicators.csv",
        ["日期", "證券代號", "Legacy"],
        [{"日期": "2024-01-01", "證券代號": "0050", "Legacy": "keep"}],
    )

    output_dir = tmp_path / "date-style-stage"
    stage_rebuild(source_db, formal_root, output_dir)

    rows = _read_csv(
        output_dir / "staged" / "technical_analysis" / "0050_indicators.csv"
    )
    assert [row["日期"] for row in rows] == ["2024-01-01", "2024-01-02"]
    assert rows[0]["Legacy"] == "keep"


def test_stage_rebuild_rejects_duplicate_source_keys_without_publishing(tmp_path):
    source_db = tmp_path / "source.sqlite"
    formal_root = tmp_path / "formal"
    (formal_root / "technical_analysis").mkdir(parents=True)
    (formal_root / "meta_data").mkdir()
    _create_source_db(source_db, duplicate_daily_key=True)
    output_dir = tmp_path / "stage"

    with pytest.raises(ValueError, match="duplicate source daily key"):
        stage_rebuild(source_db, formal_root, output_dir)

    assert not output_dir.exists()


def test_stage_rebuild_rejects_duplicate_aggregate_keys_without_publishing(
    stage_inputs, tmp_path
):
    source_db, formal_root, _technical_dir, aggregate_path = stage_inputs
    aggregate_rows = _read_csv(aggregate_path)
    aggregate_rows.append(dict(aggregate_rows[0]))
    _write_csv(aggregate_path, ["日期", "證券代號", "Legacy", "RSI"], aggregate_rows)
    output_dir = tmp_path / "duplicate-stage"

    with pytest.raises(ValueError, match="duplicate all-stocks CSV key"):
        stage_rebuild(source_db, formal_root, output_dir)

    assert not output_dir.exists()


def test_stage_rebuild_refuses_existing_or_formal_output_dir(stage_inputs, tmp_path):
    source_db, formal_root, _technical_dir, _aggregate_path = stage_inputs
    existing_output = tmp_path / "existing-stage"
    existing_output.mkdir()
    with pytest.raises(FileExistsError):
        stage_rebuild(source_db, formal_root, existing_output)
    with pytest.raises(ValueError, match="inside formal_root is allowed only"):
        stage_rebuild(source_db, formal_root, formal_root / "stage")

    with pytest.raises(ValueError, match="formal_root is allowed only"):
        stage_rebuild(
            source_db,
            formal_root,
            formal_root / "technical_analysis" / "stage",
        )


def test_stage_rebuild_allows_only_receipt_stage_subtree(stage_inputs):
    source_db, formal_root, _technical_dir, _aggregate_path = stage_inputs
    receipt_stage = (
        formal_root
        / "output"
        / "scheduled"
        / "formal_technical_repair_receipts"
        / "20260923_run01"
        / "stage"
    )

    manifest = stage_rebuild(source_db, formal_root, receipt_stage)

    assert manifest["computed_db"] == str(receipt_stage / "computed.sqlite")
    assert Path(manifest["computed_db"]).is_file()
