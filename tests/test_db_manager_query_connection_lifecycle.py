"""DBManager 查詢連線的成功／失敗生命週期回歸測試。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from data_module import db_manager as db_manager_module
from data_module.db_manager import DBManager


def _seeded_manager(tmp_path: Path) -> DBManager:
    database_path = tmp_path / "sqlite" / "twstock.db"
    log_dir = tmp_path / "logs"
    database_path.parent.mkdir(parents=True)
    log_dir.mkdir()
    manager = DBManager(
        SimpleNamespace(
            db_file=database_path,
            log_dir=log_dir,
        )
    )
    with manager.connect() as connection:
        connection.execute(
            """
            CREATE TABLE query_lifecycle_probe (
                row_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                amount REAL NOT NULL,
                nullable_text TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO query_lifecycle_probe
                (row_id, label, amount, nullable_text)
            VALUES (?, ?, ?, ?)
            """,
            [
                (1, "alpha", 1.25, None),
                (2, "beta", 2.5, "present"),
            ],
        )
    return manager


def _capture_real_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> list[sqlite3.Connection]:
    real_connect = sqlite3.connect
    captured: list[sqlite3.Connection] = []

    def capture_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        captured.append(connection)
        return connection

    monkeypatch.setattr(db_manager_module.sqlite3, "connect", capture_connect)
    return captured


def _assert_connection_is_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_execute_query_closes_real_connection_and_preserves_rows_and_dtypes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _seeded_manager(tmp_path)
    captured = _capture_real_connections(monkeypatch)

    frame = manager.execute_query(
        """
        SELECT row_id, label, amount, nullable_text
        FROM query_lifecycle_probe
        ORDER BY row_id
        """
    )

    assert frame.to_dict(orient="records") == [
        {
            "row_id": 1,
            "label": "alpha",
            "amount": 1.25,
            "nullable_text": None,
        },
        {
            "row_id": 2,
            "label": "beta",
            "amount": 2.5,
            "nullable_text": "present",
        },
    ]
    assert frame.dtypes.astype(str).to_dict() == {
        "row_id": "int64",
        "label": "object",
        "amount": "float64",
        "nullable_text": "object",
    }
    assert len(captured) == 1
    _assert_connection_is_closed(captured[0])


def test_execute_query_closes_real_connection_after_sql_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _seeded_manager(tmp_path)
    captured = _capture_real_connections(monkeypatch)

    with pytest.raises(pd.errors.DatabaseError, match="no such column"):
        manager.execute_query(
            "SELECT missing_column FROM query_lifecycle_probe"
        )

    assert len(captured) == 1
    _assert_connection_is_closed(captured[0])
