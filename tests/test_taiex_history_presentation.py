"""市場研究用 TAIEX 有界歷史 DTO 的合成契約測試。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import sqlite3

import pytest

from app_module.taiex_history_presentation import (
    TAIEX_SOURCE_ID,
    TaiexHistoryReader,
)


BASE_COLUMNS = (
    '"日期" TEXT',
    '"指數名稱" TEXT',
    '"收盤指數" REAL',
)
OHLCV_COLUMNS = (
    '"開盤價" REAL',
    '"最高價" REAL',
    '"最低價" REAL',
    '"成交量" REAL',
)


def _database(path, *, ohlcv: bool = True, companion_close: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    columns = [*BASE_COLUMNS]
    if ohlcv:
        columns.extend(OHLCV_COLUMNS)
    if companion_close:
        columns.append('"收盤價" REAL')
    connection.execute(f'CREATE TABLE market_indices ({", ".join(columns)})')
    return connection


def _insert(connection, day: str, name: str, close, *, ohlcv=None, companion=None) -> None:
    values = [day, name, close]
    if ohlcv is not None:
        values.extend(ohlcv)
    if companion is not None:
        values.append(companion)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(f"INSERT INTO market_indices VALUES ({placeholders})", values)


def test_complete_history_is_bounded_and_marks_historical_availability_unknown(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path, companion_close=True)
    _insert(
        connection,
        "20261021",
        "TAIEX",
        27000.25,
        ohlcv=(26990, 27020, 26980, 0),
        companion=27000.25,
    )
    _insert(
        connection,
        "20261022",
        "TAIEX",
        27100.5,
        ohlcv=(27010, 27110, 26999, 2500),
        companion=27100.5,
    )
    _insert(
        connection,
        "20261023",
        "TAIEX",
        28000,
        ohlcv=(27900, 28010, 27800, 3000),
        companion=28000,
    )
    _insert(
        connection,
        "20261022",
        "半導體",
        999,
        ohlcv=(990, 1000, 980, 1),
        companion=999,
    )
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22), max_sessions=1)

    assert result.source_id == TAIEX_SOURCE_ID
    assert result.requested_as_of == date(2026, 10, 22)
    assert result.effective_date == date(2026, 10, 22)
    assert [bar.trade_date for bar in result.bars] == [date(2026, 10, 22)]
    assert result.quality == "complete"
    assert result.warnings == ()
    assert result.historical_pit_eligible is False
    assert result.known_at is None
    assert result.bars[0].close == Decimal("27100.5")
    assert result.bars[0].volume == 2500


def test_close_only_legacy_schema_returns_partial_without_inventing_ohlv(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path, ohlcv=False)
    _insert(connection, "20261022", "TAIEX", "27100.25")
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "partial"
    assert result.effective_date == date(2026, 10, 22)
    assert result.bars[0].open is None
    assert result.bars[0].high is None
    assert result.bars[0].low is None
    assert result.bars[0].close == Decimal("27100.25")
    assert result.bars[0].volume is None


def test_null_ohlcv_is_preserved_and_zero_volume_is_not_treated_as_missing(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    _insert(connection, "20261021", "TAIEX", 27000, ohlcv=(None, 27010, None, 0))
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 21))

    bar = result.bars[0]
    assert result.quality == "partial"
    assert bar.open is None
    assert bar.high == Decimal("27010")
    assert bar.low is None
    assert bar.close == Decimal("27000")
    assert bar.volume == 0


@pytest.mark.parametrize(
    ("column", "field", "bad_value"),
    [
        ("開盤價", "open", 0),
        ("開盤價", "open", -1),
        ("最高價", "high", 0),
        ("最高價", "high", -1),
        ("最低價", "low", 0),
        ("最低價", "low", -1),
        ("收盤指數", "close", 0),
        ("收盤指數", "close", -1),
    ],
)
def test_nonpositive_prices_are_missing_and_mark_history_partial(
    tmp_path, column: str, field: str, bad_value: int,
) -> None:
    path = tmp_path / f"market-{field}-{bad_value}.sqlite"
    connection = _database(path)
    values = {
        "開盤價": 27000,
        "最高價": 27200,
        "最低價": 26900,
        "成交量": 1,
        "收盤指數": 27100,
    }
    values[column] = bad_value
    _insert(
        connection,
        "20261022",
        "TAIEX",
        values["收盤指數"],
        ohlcv=(values["開盤價"], values["最高價"], values["最低價"], values["成交量"]),
    )
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "partial"
    assert getattr(result.bars[0], field) is None


def test_duplicate_taiex_trade_date_fails_closed(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    _insert(connection, "20261022", "TAIEX", 27100, ohlcv=(27000, 27200, 26900, 1))
    _insert(connection, "2026-10-22", "TAIEX", 27101, ohlcv=(27000, 27200, 26900, 1))
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "unavailable"
    assert result.bars == ()
    assert "taiex_history_duplicate_date_fail_closed" in result.warnings


def test_unusually_many_duplicate_rows_fail_closed_with_bounded_read(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    connection.executemany(
        "INSERT INTO market_indices VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("20261022", "TAIEX", 27100 + index, 27000, 27200, 26900, 1)
            for index in range(500)
        ],
    )
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "unavailable"
    assert result.bars == ()
    assert result.warnings == ("taiex_history_duplicate_date_fail_closed",)


def test_other_index_is_not_returned_as_taiex(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    _insert(connection, "20261022", "半導體", 27100, ohlcv=(27000, 27200, 26900, 1))
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "missing"
    assert result.bars == ()


def test_as_of_cutoff_and_session_limit_are_applied_to_distinct_dates(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    for day, close in (
        ("20261020", 27000),
        ("20261021", 27100),
        ("20261022", 27200),
        ("20261023", 27300),
    ):
        _insert(connection, day, "TAIEX", close, ohlcv=(close, close, close, 1))
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22), max_sessions=2)

    assert [bar.trade_date for bar in result.bars] == [
        date(2026, 10, 21),
        date(2026, 10, 22),
    ]
    assert result.effective_date == date(2026, 10, 22)


def test_read_does_not_mutate_database(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    _insert(connection, "20261022", "TAIEX", 27100, ohlcv=(27000, 27200, 26900, 1))
    connection.commit()
    before = connection.execute("SELECT * FROM market_indices").fetchall()
    schema_before = connection.execute("PRAGMA table_info(market_indices)").fetchall()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    connection = sqlite3.connect(path)
    try:
        after = connection.execute("SELECT * FROM market_indices").fetchall()
        schema_after = connection.execute("PRAGMA table_info(market_indices)").fetchall()
    finally:
        connection.close()
    assert result.quality == "complete"
    assert after == before
    assert schema_after == schema_before


def test_invalid_input_date_and_session_limit_are_rejected(tmp_path) -> None:
    reader = TaiexHistoryReader(tmp_path / "missing.sqlite")

    with pytest.raises(ValueError, match="datetime.date"):
        reader.read(datetime(2026, 10, 22))
    with pytest.raises(ValueError, match="1 到 120"):
        reader.read(date(2026, 10, 22), max_sessions=121)
    with pytest.raises(ValueError, match="1 到 120"):
        reader.read(date(2026, 10, 22), max_sessions=True)


def test_missing_database_path_is_explicitly_unavailable(tmp_path) -> None:
    result = TaiexHistoryReader(None).read(date(2026, 10, 22))

    assert result.quality == "unavailable"
    assert result.bars == ()
    assert result.warnings == ("market_indices_db_path_unavailable",)


def test_missing_database_file_is_explicitly_unavailable(tmp_path) -> None:
    result = TaiexHistoryReader(tmp_path / "not-created.sqlite").read(date(2026, 10, 22))

    assert result.quality == "unavailable"
    assert result.bars == ()
    assert result.warnings[0].startswith("taiex_history_read_failed:")


def test_missing_table_and_required_schema_are_explicitly_unavailable(tmp_path) -> None:
    no_table_path = tmp_path / "no-table.sqlite"
    sqlite3.connect(no_table_path).close()
    no_table = TaiexHistoryReader(no_table_path).read(date(2026, 10, 22))
    assert no_table.quality == "unavailable"
    assert no_table.warnings == ("market_indices_table_missing",)

    schema_path = tmp_path / "bad-schema.sqlite"
    connection = sqlite3.connect(schema_path)
    connection.execute('CREATE TABLE market_indices ("日期" TEXT, "指數名稱" TEXT)')
    connection.close()
    bad_schema = TaiexHistoryReader(schema_path).read(date(2026, 10, 22))
    assert bad_schema.quality == "unavailable"
    assert bad_schema.warnings == ("market_indices_required_schema_missing",)


def test_invalid_stored_date_is_not_returned_as_a_bar(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path)
    _insert(connection, "2026-02-30", "TAIEX", 27100, ohlcv=(27000, 27200, 26900, 1))
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 3, 1))

    assert result.quality == "missing"
    assert result.bars == ()
    assert "taiex_history_invalid_trade_date_omitted" in result.warnings


def test_conflicting_close_columns_warn_and_omit_the_row(tmp_path) -> None:
    path = tmp_path / "market.sqlite"
    connection = _database(path, companion_close=True)
    _insert(
        connection,
        "20261022",
        "TAIEX",
        27100,
        ohlcv=(27000, 27200, 26900, 1),
        companion=27001,
    )
    connection.commit()
    connection.close()

    result = TaiexHistoryReader(path).read(date(2026, 10, 22))

    assert result.quality == "missing"
    assert result.effective_date is None
    assert result.bars == ()
    assert "taiex_history_conflicting_close_omitted:2026-10-22" in result.warnings
