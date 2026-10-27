from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import data_module.formal_monthly_revenue_quality_reader as reader
from data_module.fundamental_availability import FORMAL_AVAILABILITY_CONTRACT_VERSION
from data_module.fundamental_availability_sources import (
    MONTHLY_REVENUE_AVAILABILITY_COLUMNS,
)


def _create_database(path: Path, rows: tuple[tuple[object, ...], ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE fundamental_monthly_revenues (
                stock_code TEXT NOT NULL,
                period TEXT NOT NULL,
                announced_date TEXT,
                source TEXT NOT NULL DEFAULT 'fixture.monthly_revenue',
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


def _write_mops_mapping(path: Path, rows: tuple[dict[str, str], ...] = ()) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MONTHLY_REVENUE_AVAILABILITY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _mops_mapping_row(
    *,
    stock_code: str = "2330",
    period: str = "2026-04",
    target_source_version: str = "source-v2",
    source: str = "mops.monthly_revenue_announcement",
) -> dict[str, str]:
    return {
        "stock_code": stock_code,
        "period": period,
        "as_of_date": f"{period}-30",
        "announced_date": "2026-05-08",
        "available_date": "2026-05-09",
        "source": source,
        "source_version": "mops-event-2026-05-08",
        "announced_at": "2026-05-08T14:40:12+08:00",
        "target_source_version": target_source_version,
        "availability_contract_version": FORMAL_AVAILABILITY_CONTRACT_VERSION,
        "evidence_class": "official_announcement",
        "source_hash": "sha256:" + "a" * 64,
        "revision": "1",
        "parent_revision": "",
    }


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
                "report_level_date_unverified_row_count": 0,
                "distinct_stock_code_count": 2,
                "distinct_source_version_count": 2,
            },
            {
                "period": "2026-02",
                "formal_row_count": 1,
                "missing_announcement_date_row_count": 1,
                "report_level_date_unverified_row_count": 0,
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


def test_summary_flags_report_level_snapshot_dates_as_unverified(tmp_path: Path) -> None:
    database = tmp_path / "formal-report-level-dates.db"
    _create_database(
        database,
        (
            ("2330", "2026-05", "2026-06-16", "snapshot-v1", "private-a"),
            ("2317", "2026-05", "2026-06-16", "snapshot-v1", "private-b"),
        ),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_monthly_revenues "
            "SET source = 'mops.monthly_revenue_static_snapshot'"
        )

    result = reader.read_formal_monthly_revenue_quality_by_period(database)

    assert result["status"] == "observed"
    assert result["periods"] == [
        {
            "period": "2026-05",
            "formal_row_count": 2,
            "missing_announcement_date_row_count": 0,
            "report_level_date_unverified_row_count": 2,
            "distinct_stock_code_count": 2,
            "distinct_source_version_count": 1,
        }
    ]
    assert "private-" not in repr(result)


def test_summary_uses_exact_mops_mapping_identity_to_resolve_report_date_doubt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-report-level-date-mapping.db"
    mapping = tmp_path / "availability.csv"
    _create_database(
        database,
        (
            ("2330", "2026-04", "2026-05-08", "snapshot-v1", "private-a"),
            ("2317", "2026-04", "2026-06-16", "snapshot-v1", "private-b"),
        ),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_monthly_revenues "
            "SET source = 'mops.monthly_revenue_static_snapshot'"
        )
    _write_mops_mapping(
        mapping,
        (
            _mops_mapping_row(
                stock_code="2330",
                period="2026-04",
                target_source_version="snapshot-v1",
            ),
        ),
    )

    result = reader.read_formal_monthly_revenue_quality_by_period(database, mapping)

    assert result["periods"][0]["report_level_date_unverified_row_count"] == 1
    assert "private-" not in repr(result)


def test_summary_keeps_report_date_unverified_when_exact_mapping_date_differs(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-report-level-date-mismatch.db"
    mapping = tmp_path / "availability.csv"
    _create_database(
        database,
        (("2330", "2026-04", "2026-06-16", "snapshot-v1", "private-a"),),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_monthly_revenues "
            "SET source = 'mops.monthly_revenue_static_snapshot'"
        )
    _write_mops_mapping(
        mapping,
        (_mops_mapping_row(target_source_version="snapshot-v1"),),
    )

    result = reader.read_formal_monthly_revenue_quality_by_period(database, mapping)

    assert result["periods"][0]["report_level_date_unverified_row_count"] == 1


def test_quality_details_include_missing_and_report_level_date_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-quality-details.db"
    mapping = tmp_path / "availability.csv"
    _create_database(
        database,
        (
            ("2330", "2026-04", "2026-05-08", "snapshot-v1", "private-a"),
            ("2317", "2026-04", "2026-06-16", "snapshot-v1", "private-b"),
            ("2881", "2026-04", None, "source-v2", "private-c"),
        ),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE fundamental_monthly_revenues "
            "SET source = CASE stock_code "
            "WHEN '2330' THEN 'mops.monthly_revenue_static_snapshot' "
            "WHEN '2317' THEN 'mops.monthly_revenue_static_snapshot' "
            "ELSE 'mops.monthly_revenue_announcement' END"
        )
    _write_mops_mapping(
        mapping,
        (
            _mops_mapping_row(stock_code="2330", target_source_version="snapshot-v1"),
            _mops_mapping_row(stock_code="2317", target_source_version="snapshot-v1"),
            _mops_mapping_row(stock_code="2881", target_source_version="source-v2"),
        ),
    )

    result = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, "2026-04", availability_mapping_path=mapping
    )

    assert result["total_count"] == 3
    assert result["rows"] == [
        {
            "stock_code": "2317",
            "source": "mops.monthly_revenue_static_snapshot",
            "source_version": "snapshot-v1",
            "stored_announced_date": "2026-06-16",
            "mapping_match_state": "exact_mapping_date_differs",
            "mapping_announced_date": "2026-05-08",
        },
        {
            "stock_code": "2330",
            "source": "mops.monthly_revenue_static_snapshot",
            "source_version": "snapshot-v1",
            "stored_announced_date": "2026-05-08",
            "mapping_match_state": "exact_mapping_date_matches",
            "mapping_announced_date": "2026-05-08",
        },
        {
            "stock_code": "2881",
            "source": "mops.monthly_revenue_announcement",
            "source_version": "source-v2",
            "stored_announced_date": None,
            "mapping_match_state": "exact_version_mapping_present",
            "mapping_announced_date": "2026-05-08",
        },
    ]
    assert "private-" not in repr(result)


def test_missing_announcement_details_are_paged_and_exclude_values(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-details.db"
    _create_database(
        database,
        (
            ("2330", "2026-04", None, "source-v2", "private-value-a"),
            ("2317", "2026-04", "", "source-v1", "private-value-b"),
            ("2330", "2026-04", None, "source-v1", "private-value-c"),
            ("2317", "2026-04", "2026-05-12", "source-v3", "private-value-d"),
            ("2330", "2026-05", None, "source-v4", "private-value-e"),
        ),
    )

    first_page = reader.read_formal_monthly_revenue_quality_missing_rows(
        database,
        period="2026-04",
        limit=2,
        offset=0,
    )
    second_page = reader.read_formal_monthly_revenue_quality_missing_rows(
        database,
        period="2026-04",
        limit=2,
        offset=2,
    )

    assert first_page == {
        "schema_version": reader.FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
        "status": "observed",
        "period": "2026-04",
        "mapping_status": "not_configured",
        "rows": [
            {
                "stock_code": "2317",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v1",
                "stored_announced_date": "",
                "mapping_match_state": "unknown",
                "mapping_announced_date": None,
            },
            {
                "stock_code": "2330",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v1",
                "stored_announced_date": None,
                "mapping_match_state": "unknown",
                "mapping_announced_date": None,
            },
        ],
        "total_count": 3,
        "limit": 2,
        "offset": 0,
        "has_more": True,
        "blockers": [],
        "scope": "formal_monthly_revenue_announcement_quality_identity_page",
        "formal_db_write": False,
        "financial_values_returned": False,
    }
    assert second_page["rows"] == [
        {
            "stock_code": "2330",
            "source": "fixture.monthly_revenue",
            "source_version": "source-v2",
            "stored_announced_date": None,
            "mapping_match_state": "unknown",
            "mapping_announced_date": None,
        }
    ]
    assert second_page["has_more"] is False
    assert "private-value" not in repr(first_page)
    assert "private-value" not in repr(second_page)


def test_missing_details_match_only_exact_company_period_and_target_source_version(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-exact-mapping.db"
    mapping = tmp_path / "availability.csv"
    _create_database(
        database,
        (
            ("2330", "2026-04", None, "source-v2", "private-a"),
            ("2330", "2026-04", None, "source-v1", "private-b"),
            ("2317", "2026-04", None, "source-v2", "private-c"),
            ("2330", "2026-05", None, "source-v2", "private-d"),
        ),
    )
    _write_mops_mapping(
        mapping,
        (_mops_mapping_row(target_source_version="source-v2"),),
    )

    result = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, period="2026-04", availability_mapping_path=mapping
    )

    assert result["schema_version"] == reader.FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA
    assert result["mapping_status"] == "verified"
    assert result["rows"] == [
        {
            "stock_code": "2317",
            "source": "fixture.monthly_revenue",
            "source_version": "source-v2",
            "stored_announced_date": None,
            "mapping_match_state": "no_exact_version_mapping",
            "mapping_announced_date": None,
        },
        {
            "stock_code": "2330",
            "source": "fixture.monthly_revenue",
            "source_version": "source-v1",
            "stored_announced_date": None,
            "mapping_match_state": "no_exact_version_mapping",
            "mapping_announced_date": None,
        },
        {
            "stock_code": "2330",
            "source": "fixture.monthly_revenue",
            "source_version": "source-v2",
            "stored_announced_date": None,
            "mapping_match_state": "exact_version_mapping_present",
            "mapping_announced_date": "2026-05-08",
        },
    ]
    assert "private-" not in repr(result)


def test_missing_details_distinguish_verified_no_match_from_unknown_mapping(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-mapping-status.db"
    empty_mapping = tmp_path / "empty-availability.csv"
    missing_mapping = tmp_path / "missing-availability.csv"
    _create_database(
        database,
        (("2330", "2026-04", None, "source-v1", "private-a"),),
    )
    _write_mops_mapping(empty_mapping)

    no_match = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, "2026-04", availability_mapping_path=empty_mapping
    )
    unavailable = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, "2026-04", availability_mapping_path=missing_mapping
    )
    unconfigured = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, "2026-04"
    )

    assert no_match["mapping_status"] == "verified"
    assert no_match["rows"][0]["mapping_match_state"] == "no_exact_version_mapping"
    for result, expected_status in (
        (unavailable, "unavailable"),
        (unconfigured, "not_configured"),
    ):
        assert result["mapping_status"] == expected_status
        assert result["rows"][0]["mapping_match_state"] == "unknown"
        assert result["rows"][0]["mapping_announced_date"] is None


def test_any_mapping_diagnostic_keeps_all_detail_matches_unknown(tmp_path: Path) -> None:
    database = tmp_path / "formal-diagnostic-mapping.db"
    mapping = tmp_path / "diagnostic-availability.csv"
    _create_database(
        database,
        (("2330", "2026-04", None, "source-v2", "private-a"),),
    )
    invalid_row = _mops_mapping_row(target_source_version="")
    _write_mops_mapping(
        mapping,
        (
            _mops_mapping_row(target_source_version="source-v2"),
            invalid_row,
        ),
    )

    result = reader.read_formal_monthly_revenue_quality_missing_rows(
        database, "2026-04", availability_mapping_path=mapping
    )

    assert result["mapping_status"] == "invalid"
    assert result["rows"][0]["mapping_match_state"] == "unknown"
    assert result["rows"][0]["mapping_announced_date"] is None


def test_missing_announcement_details_reject_invalid_period_and_page_bounds(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-invalid-page.db"
    _create_database(database, ())

    invalid_period = reader.read_formal_monthly_revenue_quality_missing_rows(
        database,
        period="2026-13",
    )
    oversized_page = reader.read_formal_monthly_revenue_quality_missing_rows(
        database,
        period="2026-04",
        limit=reader.MAX_DETAIL_PAGE_SIZE + 1,
    )
    oversized_offset = reader.read_formal_monthly_revenue_quality_missing_rows(
        database,
        period="2026-04",
        offset=reader.MAX_DETAIL_OFFSET + 1,
    )

    for result in (invalid_period, oversized_page, oversized_offset):
        assert result["status"] == "unavailable"
        assert result["rows"] is None
        assert result["formal_db_write"] is False
        assert result["financial_values_returned"] is False


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
