from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import data_module.formal_announcement_impact_reader as reader
from data_module.open_data_quarterly_announcement_crosswalk import AUDIT_SCHEMA


def _crosswalk(
    *,
    status: str = "one_announcement_candidate",
    period: str = "2025-Q2",
    stock_code: str = "2330",
    event_hash: str = "a" * 64,
    source_hash: str = "b" * 64,
) -> dict[str, object]:
    candidates = (
        [
            {
                "announcement_at": "2025-08-14T14:00:00+08:00",
                "event_sha256": event_hash,
                "source_sha256": source_hash,
            }
        ]
        if status == "one_announcement_candidate"
        else [
            {
                "announcement_at": "2025-08-14T14:00:00+08:00",
                "event_sha256": event_hash,
                "source_sha256": source_hash,
            },
            {
                "announcement_at": "2025-08-15T14:00:00+08:00",
                "event_sha256": "c" * 64,
                "source_sha256": source_hash,
            },
        ]
    )
    row = {
        "issuer_code": stock_code,
        "fiscal_period": period,
        "status": status,
        "announcement_timestamp_resolution": (
            "unique_candidate_timestamp"
            if status == "one_announcement_candidate"
            else "ambiguous_candidate_versions"
        ),
        "announcement_count": len(candidates),
        "announcement_candidates": candidates,
    }
    return {
        "schema_version": AUDIT_SCHEMA,
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "status": "available",
        "resources": [
            {
                "market": "TWSE",
                "statement": "income_statement",
                "rows": [row],
            }
        ],
    }


def _create_formal_db(path: Path, rows: tuple[tuple[object, ...], ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE fundamental_statement_items (
                stock_code TEXT NOT NULL,
                statement_type TEXT NOT NULL,
                period TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                announced_date TEXT,
                available_date TEXT NOT NULL,
                item_code TEXT NOT NULL,
                item_name TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                source_version TEXT NOT NULL,
                quality TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO fundamental_statement_items (
                stock_code, statement_type, period, as_of_date, announced_date,
                available_date, item_code, item_name, value, source,
                source_version, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _formal_row(
    *, item_code: str, value: str, source_version: str, announced_date: str | None
) -> tuple[object, ...]:
    return (
        "2330",
        "income_statement",
        "2025-Q2",
        "2025-06-30",
        announced_date,
        "2025-08-14",
        item_code,
        f"item-{item_code}",
        value,
        "mops.financial_statement.raw",
        source_version,
        "degraded",
    )


def test_reads_only_bounded_identity_aggregates_without_clearing_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal.db"
    _create_formal_db(
        database,
        (
            _formal_row(
                item_code="REV",
                value="DO_NOT_RETURN_123",
                source_version="mops:content:111",
                announced_date=None,
            ),
            _formal_row(
                item_code="EPS",
                value="DO_NOT_RETURN_456",
                source_version="mops:content:111",
                announced_date="",
            ),
            _formal_row(
                item_code="ASSET",
                value="DO_NOT_RETURN_789",
                source_version="mops:content:222",
                announced_date="2025-08-14",
            ),
        ),
    )
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(), database_path=database
    )

    assert result["status"] == "observed"
    assert result["candidate_unique_keys"] == 1
    assert result["formal_identity_overlap"] == 1
    assert result["formal_version_count"] == 2
    assert result["formal_item_rows"] == 3
    assert result["missing_announcement_date_rows"] == 2
    assert result["exact_version_links"] == 0
    assert result["rows_cleared"] == 0
    assert "candidate_event_to_content_version_bridge_missing" in result["blockers"]
    assert "formal_table_has_no_market_column_identity_only_overlap" in result["blockers"]
    assert "DO_NOT_RETURN" not in repr(result)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_roc_quarter_is_normalized_to_formal_gregorian_period(tmp_path: Path) -> None:
    database = tmp_path / "formal.db"
    _create_formal_db(
        database,
        (
            _formal_row(
                item_code="REV",
                value="not-returned",
                source_version="mops:content:111",
                announced_date=None,
            ),
        ),
    )

    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(period="114-Q2"), database_path=database
    )

    assert result["status"] == "observed"
    assert result["candidate_unique_keys"] == 1
    assert result["formal_identity_overlap"] == 1
    assert result["formal_item_rows"] == 1
    assert result["missing_announcement_date_rows"] == 1
    assert result["rows_cleared"] == 0


def test_ambiguous_announcement_is_not_counted_and_is_not_evaluated(
    tmp_path: Path,
) -> None:
    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(status="multiple_announcement_candidates"),
        database_path=tmp_path / "does-not-exist.db",
    )

    assert result["status"] == "not_evaluated"
    assert result["candidate_unique_keys"] == 0
    assert result["formal_identity_overlap"] is None
    assert result["rows_cleared"] is None


def test_unavailable_database_returns_unknown_counts_not_zero(tmp_path: Path) -> None:
    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(), database_path=tmp_path / "missing.db"
    )

    assert result["status"] == "unavailable"
    assert result["candidate_unique_keys"] is None
    assert result["formal_identity_overlap"] is None
    assert result["formal_item_rows"] is None
    assert result["missing_announcement_date_rows"] is None
    assert result["exact_version_links"] is None
    assert result["rows_cleared"] is None


def test_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "wrong-schema.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE fundamental_statement_items (value TEXT)")

    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(), database_path=database
    )

    assert result["status"] == "unavailable"
    assert result["formal_identity_overlap"] is None
    assert result["rows_cleared"] is None
    assert "formal_database_or_schema_unavailable" in result["blockers"]


def test_invalid_unique_candidate_hash_fails_closed(tmp_path: Path) -> None:
    crosswalk = _crosswalk(event_hash="not-a-sha")

    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=crosswalk, database_path=tmp_path / "does-not-exist.db"
    )

    assert result["status"] == "unavailable"
    assert result["candidate_unique_keys"] is None
    assert "unique_announcement_candidate_event_hash_invalid" in result["blockers"]


def test_candidate_scope_limit_fails_closed(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(reader, "MAX_CANDIDATE_KEYS", 0)

    result = reader.read_quarterly_announcement_formal_impact(
        crosswalk=_crosswalk(), database_path=tmp_path / "does-not-exist.db"
    )

    assert result["status"] == "unavailable"
    assert result["candidate_unique_keys"] is None
    assert "candidate_identity_scope_exceeded" in result["blockers"]
