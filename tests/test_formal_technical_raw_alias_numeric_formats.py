"""Raw alias numeric and explicit missing-value contract tests."""

from __future__ import annotations

import csv
import sqlite3

import pytest

from data_module import formal_technical_raw_alias_repair as repair


@pytest.mark.parametrize(
    ("value", "column", "expected"),
    [
        ("1,234.56", "最後揭示買價", "1234.56"),
        ("-1,234.500", "最後揭示賣價", "-1234.5"),
        ("1,234", "最後揭示買量", "1234"),
        ("+12,000", "最後揭示賣量", "12000"),
        ("1.2300e+2", "本益比", "123"),
        ("-0.00", "漲跌價差", "0"),
        (1234.56, "最後揭示買價", "1234.56"),
    ],
)
def test_numeric_text_accepts_decimal_and_correct_thousands_grouping(value, column, expected):
    assert repair._numeric_text(value, column) == expected


@pytest.mark.parametrize("column", ["最後揭示買價", "最後揭示賣價"])
def test_official_no_quote_marker_is_missing_only_for_bid_ask_prices(column):
    assert repair._numeric_text("--", column) == ""
    assert repair._same_numeric("--", None, column)


@pytest.mark.parametrize("value", [None, "", "   ", float("nan")])
def test_explicit_null_representations_are_missing(value):
    assert repair._numeric_text(value, "最後揭示買價") == ""
    assert repair._numeric_text(value, "本益比") == ""


@pytest.mark.parametrize(
    ("value", "column"),
    [
        ("--", "本益比"),
        ("--", "最後揭示買量"),
        ("nan", "最後揭示買價"),
        ("NaN", "本益比"),
        ("null", "最後揭示賣價"),
        ("none", "最後揭示賣量"),
        ("<NA>", "漲跌價差"),
        ("N/A", "本益比"),
        (float("inf"), "本益比"),
    ],
)
def test_non_numeric_text_and_non_finite_numbers_are_rejected(value, column):
    with pytest.raises(repair.RawAliasRepairError):
        repair._numeric_text(value, column)


@pytest.mark.parametrize(
    "value",
    ["12,34", "1,234,56", "1234,567", "1,,234", "1,234.5,6", "1.234,56"],
)
def test_malformed_thousands_grouping_is_rejected(value):
    with pytest.raises(repair.RawAliasRepairError):
        repair._numeric_text(value, "最後揭示買價")


def test_numeric_comparison_uses_exact_decimal_values_and_column_missing_rules():
    assert repair._same_numeric("1,234.50", 1234.5, "最後揭示買價")
    assert repair._same_numeric("1,234", 1234, "最後揭示買量")
    assert not repair._same_numeric("1,234.50", 1234.51, "最後揭示買價")
    assert not repair._same_numeric("--", None, "本益比")
    assert not repair._same_numeric("--", None)


def test_numeric_spool_converts_official_missing_and_grouped_text_to_typed_values():
    source = sqlite3.connect(":memory:")
    source.execute(
        'CREATE TABLE daily_prices ('
        '"最後揭示買價" REAL,"最後揭示買量" INTEGER,"最後揭示賣價" REAL,'
        '"最後揭示賣量" INTEGER,"本益比" REAL,"漲跌價差" REAL)'
    )
    source.execute(
        "INSERT INTO daily_prices VALUES (?,?,?,?,?,?)",
        ("--", "1,234", "1,234.50", None, 12.5, "-0.25"),
    )
    raw = source.execute("SELECT * FROM daily_prices").fetchone()
    assert raw == ("--", "1,234", "1,234.50", None, 12.5, -0.25)

    spool = sqlite3.connect(":memory:")
    repair._spool_schema(spool)
    canonical = tuple(
        repair._numeric_storage_value(value, column)
        for column, value in zip(repair.ALIASES, raw, strict=True)
    )
    spool.execute(
        "INSERT INTO canonical_aliases VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("20260520", "2330", "20260520", "2330", *canonical),
    )
    actual = spool.execute(
        'SELECT "最後揭示買價","最後揭示買量","最後揭示賣價",'
        '"最後揭示賣量","本益比","漲跌價差" FROM canonical_aliases'
    ).fetchone()
    assert actual == (None, 1234, 1234.5, None, 12.5, -0.25)
    storage = spool.execute(
        'SELECT typeof("最後揭示買價"),typeof("最後揭示買量"),'
        'typeof("最後揭示賣價"),typeof("最後揭示賣量"),'
        'typeof("本益比"),typeof("漲跌價差") FROM canonical_aliases'
    ).fetchone()
    assert storage == ("null", "integer", "real", "null", "real", "real")


def test_real_column_spool_rejects_decimal_precision_lost_by_float_storage():
    with pytest.raises(repair.RawAliasRepairError, match="無法在 SQLite REAL 中精確往返"):
        repair._numeric_storage_value("1,234.567890123456789", "最後揭示買價")


def _write_alias_csv(path, *, short_row):
    fields = [*repair.KEYS, *repair.ALIASES]
    values = ["20260520", "2330", "10", "2", "11", "3", "12.5", "0.5"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerow(values[:-1] if short_row else values)
    return fields


def _write_canonical_alias_spool(path):
    with sqlite3.connect(path) as spool:
        repair._spool_schema(spool)
        spool.execute(
            "INSERT INTO canonical_aliases VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("20260520", "2330", "20260520", "2330", 10.0, 2, 11.0, 3, 12.5, 0.5),
        )


def test_stage_rejects_dictreader_short_row_even_when_missing_tail_is_optional(tmp_path):
    target = tmp_path / "before.csv"
    _write_alias_csv(target, short_row=True)
    staged = tmp_path / "receipt" / "stage" / "technical_analysis" / "2330.csv"
    with sqlite3.connect(":memory:") as spool:
        repair._spool_schema(spool)
        spool.execute(
            "INSERT INTO canonical_aliases VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("20260520", "2330", "20260520", "2330", 10.0, 2, 11.0, 3, 12.5, 0.5),
        )
        with pytest.raises(repair.RawAliasRepairError, match="stage CSV 資料列短於標頭"):
            repair._stage_csv_target(
                root=tmp_path,
                target=target,
                staged=staged,
                expected_before_sha=repair._file_hash(target),
                spool=spool,
                order="symbol_date",
                symbol="2330",
            )


def test_audit_rejects_dictreader_short_row(tmp_path):
    before = tmp_path / "before.csv"
    staged = tmp_path / "staged.csv"
    _write_alias_csv(before, short_row=True)
    _write_alias_csv(staged, short_row=False)
    spool_path = tmp_path / "spool.sqlite"
    _write_canonical_alias_spool(spool_path)
    with pytest.raises(repair.RawAliasRepairError, match="audit CSV 資料列短於標頭"):
        repair._audit_csv_target(
            target=before,
            staged=staged,
            expected_before_sha=repair._file_hash(before),
            expected_after_sha=repair._file_hash(staged),
            spool_path=spool_path,
            order="symbol_date",
            symbol="2330",
        )
