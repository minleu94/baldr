from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from app_module.backtest_repository import BacktestRunRepository


def _repository(tmp_path):
    db_path = tmp_path / "backtest_runs.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                stock_code TEXT,
                strategy_id TEXT,
                strategy_params TEXT,
                tags TEXT,
                created_at TEXT
            )
            """
        )
    repository = object.__new__(BacktestRunRepository)
    repository.db_path = db_path
    return repository, db_path


def _insert_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    created_at: str | None,
    stock_code: str = "2330",
    strategy_id: str = "strategy-a",
) -> None:
    connection.execute(
        """
        INSERT INTO runs (
            run_id, run_name, stock_code, strategy_id, strategy_params, tags, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, run_id, stock_code, strategy_id, json.dumps({"window": 20}), "[]", created_at),
    )


def _row_cursor(row: dict[str, object]) -> tuple[str, str]:
    return str(row.get("created_at") or ""), str(row["run_id"])


def test_list_runs_keyset_cursor_reads_three_pages_without_repeating_after_new_insert(tmp_path) -> None:
    repository, db_path = _repository(tmp_path)
    start = datetime(2026, 1, 1)
    with sqlite3.connect(db_path) as connection:
        for index in range(111):
            created_at = (start + timedelta(minutes=index)).isoformat()
            _insert_run(connection, run_id=f"run-{index:03d}", created_at=created_at)

    legacy_default = repository.list_runs()
    legacy_positional = repository.list_runs(None, None, 100)
    assert len(legacy_default) == 100
    assert len(legacy_positional) == 100
    assert legacy_default[0]["strategy_params"] == {"window": 20}
    assert legacy_default[0]["tags"] == []

    first_page = repository.list_runs(limit=50)
    assert len(first_page) == 50
    assert [row["run_id"] for row in first_page[:2]] == ["run-110", "run-109"]

    with sqlite3.connect(db_path) as connection:
        _insert_run(
            connection,
            run_id="run-inserted-later",
            created_at=(start + timedelta(days=1)).isoformat(),
        )

    second_page = repository.list_runs(limit=50, cursor=_row_cursor(first_page[-1]))
    third_page = repository.list_runs(limit=50, cursor=_row_cursor(second_page[-1]))
    assert len(second_page) == 50
    assert len(third_page) == 11
    assert "run-inserted-later" not in {
        row["run_id"] for row in (*first_page, *second_page, *third_page)
    }

    original_ids = [row["run_id"] for row in (*first_page, *second_page, *third_page)]
    assert len(original_ids) == 111
    assert len(set(original_ids)) == 111
    assert original_ids == [f"run-{index:03d}" for index in range(110, -1, -1)]


def test_list_runs_cursor_orders_equal_and_null_dates_by_run_id(tmp_path) -> None:
    repository, db_path = _repository(tmp_path)
    with sqlite3.connect(db_path) as connection:
        for run_id in ("same-A", "same-C", "same-B"):
            _insert_run(connection, run_id=run_id, created_at="2026-07-01T12:00:00")
        for run_id in ("null-A", "null-C", "null-B"):
            _insert_run(connection, run_id=run_id, created_at=None)

    first_page = repository.list_runs(limit=2)
    second_page = repository.list_runs(limit=2, cursor=_row_cursor(first_page[-1]))
    third_page = repository.list_runs(limit=2, cursor=_row_cursor(second_page[-1]))

    assert [row["run_id"] for row in first_page] == ["same-C", "same-B"]
    assert [row["run_id"] for row in second_page] == ["same-A", "null-C"]
    assert [row["run_id"] for row in third_page] == ["null-B", "null-A"]
    assert [row["created_at"] for row in second_page[-1:]] == [None]
    assert _row_cursor(second_page[-1]) == ("", "null-C")


def test_list_runs_cursor_respects_strategy_and_stock_filters(tmp_path) -> None:
    repository, db_path = _repository(tmp_path)
    with sqlite3.connect(db_path) as connection:
        rows = (
            ("a-new", "2026-07-03", "2330", "strategy-a"),
            ("a-mid", "2026-07-02", "2330", "strategy-a"),
            ("a-old", "2026-07-01", "2330", "strategy-a"),
            ("other-stock", "2026-07-04", "2317", "strategy-a"),
            ("other-strategy", "2026-07-05", "2330", "strategy-b"),
        )
        for run_id, created_at, stock_code, strategy_id in rows:
            _insert_run(
                connection,
                run_id=run_id,
                created_at=created_at,
                stock_code=stock_code,
                strategy_id=strategy_id,
            )

    first_page = repository.list_runs(
        strategy_id="strategy-a", stock_code="2330", limit=1
    )
    second_page = repository.list_runs(
        strategy_id="strategy-a",
        stock_code="2330",
        limit=2,
        cursor=_row_cursor(first_page[-1]),
    )

    assert [row["run_id"] for row in first_page] == ["a-new"]
    assert [row["run_id"] for row in second_page] == ["a-mid", "a-old"]
    assert all(row["strategy_id"] == "strategy-a" for row in (*first_page, *second_page))
    assert all(row["stock_code"] == "2330" for row in (*first_page, *second_page))


@pytest.mark.parametrize("bad_cursor", [("2026-01-01",), ("2026-01-01", "id", "extra"), ["2026-01-01", "id"]])
def test_list_runs_rejects_malformed_cursor(tmp_path, bad_cursor) -> None:
    repository, _db_path = _repository(tmp_path)

    with pytest.raises(ValueError, match="cursor 必須"):
        repository.list_runs(cursor=bad_cursor)  # type: ignore[arg-type]
