from __future__ import annotations

import sqlite3
from pathlib import Path

import data_module.formal_monthly_revenue_quality_reader as reader


def _create_database(path: Path, rows: tuple[tuple[object, ...], ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE fundamental_monthly_revenues (
                stock_code TEXT NOT NULL,
                period TEXT NOT NULL,
                announced_date TEXT,
                source_version TEXT NOT NULL,
                revenue TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO fundamental_monthly_revenues (
                stock_code, period, announced_date, source_version, revenue
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_returns_stably_sorted_monthly_aggregates_without_financial_values(
    tmp_path: Path,
) -> None:
    database = tmp_path / "synthetic-formal.db"
    _create_database(
        database,
        (
            ("2330", "2026-02", None, "source-v1", "private-value-a"),
            ("2317", "2026-01", "2026-02-10", "source-v1", "private-value-b"),
            ("2330", "2026-01", "", "source-v2", "private-value-c"),
            ("2330", "2026-01", "2026-02-11", "source-v1", "private-value-d"),
        ),
    )

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result == {
        "schema_version": reader.FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA,
        "status": "observed",
        "periods": [
            {
                "period": "2026-01",
                "formal_row_count": 3,
                "missing_announcement_date_row_count": 1,
                "distinct_stock_code_count": 2,
                "distinct_source_version_count": 2,
            },
            {
                "period": "2026-02",
                "formal_row_count": 1,
                "missing_announcement_date_row_count": 1,
                "distinct_stock_code_count": 1,
                "distinct_source_version_count": 1,
            },
        ],
        "blockers": [],
        "scope": "formal_monthly_revenue_rows_grouped_by_period",
        "formal_db_write": False,
        "financial_values_returned": False,
    }
    assert "private-value" not in repr(result)


def test_missing_database_fails_closed_without_creating_it(tmp_path: Path) -> None:
    missing_database = tmp_path / "missing.db"

    result = reader.read_formal_monthly_revenue_quality_by_period(missing_database)

    assert result["status"] == "unavailable"
    assert result["periods"] is None
    assert result["blockers"]
    assert result["formal_db_write"] is False
    assert result["financial_values_returned"] is False
    assert not missing_database.exists()


def test_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "wrong-schema.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE fundamental_monthly_revenues "
            "(stock_code TEXT NOT NULL, period TEXT NOT NULL, revenue TEXT NOT NULL)"
        )

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result["status"] == "unavailable"
    assert result["periods"] is None
    assert result["blockers"] == [
        "formal_monthly_revenue_database_or_schema_unavailable"
    ]


def test_invalid_period_or_storage_types_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "invalid-period.db"
    _create_database(
        database,
        (("2330", "2026-13", None, "source-v1", "private-value"),),
    )

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result["status"] == "unavailable"
    assert result["periods"] is None
    assert result["formal_db_write"] is False
    assert result["financial_values_returned"] is False


def test_runtime_storage_type_mismatch_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "invalid-storage-type.db"
    _create_database(
        database,
        ((sqlite3.Binary(b"2330"), "2026-01", None, "source-v1", "private-value"),),
    )

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result["status"] == "unavailable"
    assert result["periods"] is None


def test_query_only_reader_cannot_write(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "query-only.db"
    _create_database(database, (("2330", "2026-01", None, "source-v1", "x"),))
    original_connect = sqlite3.connect
    observed_query_only: list[int] = []
    observed_uris: list[str] = []

    class QueryOnlyGuard:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def __enter__(self) -> "QueryOnlyGuard":
            return self

        def __exit__(self, *args: object) -> object:
            return self._connection.__exit__(*args)

        def execute(self, sql: str, parameters: tuple[object, ...] = ()):
            if sql == "PRAGMA query_only":
                result = self._connection.execute(sql, parameters)
                observed_query_only.append(int(result.fetchone()[0]))
                return _OneRowCursor((observed_query_only[-1],))
            return self._connection.execute(sql, parameters)

        @property
        def row_factory(self):
            return self._connection.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self._connection.row_factory = value

    class _OneRowCursor:
        def __init__(self, row: tuple[int]) -> None:
            self._row = row

        def fetchone(self) -> tuple[int]:
            return self._row

    def guarded_connect(*args: object, **kwargs: object) -> QueryOnlyGuard:
        observed_uris.append(str(args[0]))
        return QueryOnlyGuard(original_connect(*args, **kwargs))

    monkeypatch.setattr(reader.sqlite3, "connect", guarded_connect)

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result["status"] == "observed"
    assert observed_query_only == [1]
    assert observed_uris == [database.resolve().as_uri() + "?mode=ro"]
