from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from app_module.research_console_source_service import ResearchConsoleSourceService
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    ReadOnlySQLiteManager,
    check_read_cancelled,
    connect_read_only_sqlite,
    cooperative_read_cancellation,
)
from ui_qt.workers.task_worker import TaskWorker


def test_task_worker_cancels_real_recursive_sql_and_closes_readonly_connection(
    tmp_path: Path,
) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    db_path = tmp_path / "long_read.db"
    with closing(sqlite3.connect(db_path)) as writer, writer:
        writer.execute("CREATE TABLE seed (value INTEGER NOT NULL)")
        writer.execute("INSERT INTO seed(value) VALUES (1)")

    query_started = threading.Event()
    cancelled = threading.Event()
    native_finished = threading.Event()
    errors: list[str] = []
    state: dict[str, bool] = {}

    def read_recursive_cte(cancel_callback=None) -> None:
        with cooperative_read_cancellation(cancel_callback):
            conn = connect_read_only_sqlite(db_path)
            try:
                query_started.set()
                conn.execute(
                    """
                    WITH RECURSIVE endless(value) AS (
                        SELECT 1
                        UNION ALL
                        SELECT value + 1 FROM endless
                    )
                    SELECT sum(value) FROM endless
                    """
                ).fetchone()
            finally:
                conn.close()
                try:
                    conn.execute("SELECT 1")
                except sqlite3.ProgrammingError as exc:
                    state["closed_in_worker"] = "closed database" in str(exc).lower()

    worker = TaskWorker(read_recursive_cte)
    worker.cancelled.connect(cancelled.set)
    worker.error.connect(errors.append)
    worker.native_thread_finished.connect(native_finished.set)
    worker.start()

    try:
        assert query_started.wait(3), "worker did not enter the recursive SQL query"
        time.sleep(0.03)
        worker.cancel(wait=False)
        assert worker.wait(5000), "SQLite progress handler did not stop the query promptly"
        app.processEvents()
        assert cancelled.is_set()
        assert native_finished.is_set()
        assert errors == []
        assert state["closed_in_worker"] is True
    finally:
        if worker.isRunning():
            worker.cancel(wait=False)
            worker.wait(5000)
        app.processEvents()


def test_cancellation_scope_resets_and_readonly_helper_preserves_read_contract(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "scope_reset.db"
    with closing(sqlite3.connect(db_path)) as writer, writer:
        writer.execute("CREATE TABLE values_table (value INTEGER NOT NULL)")
        writer.execute("INSERT INTO values_table(value) VALUES (7)")

    requested = False
    with cooperative_read_cancellation(lambda: requested):
        conn = connect_read_only_sqlite(db_path)
        try:
            assert conn.execute("SELECT value FROM values_table").fetchone()[0] == 7
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("INSERT INTO values_table(value) VALUES (8)")
        finally:
            conn.close()

    requested = True
    check_read_cancelled()
    assert ReadOnlySQLiteManager(db_path).execute_query(
        "SELECT value FROM values_table"
    )["value"].tolist() == [7]


def test_readonly_helper_keeps_missing_database_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connect_read_only_sqlite(tmp_path / "missing.db")


def test_research_console_placeholder_does_not_call_providers() -> None:
    calls: list[str] = []

    def provider() -> None:
        calls.append("projection")
        raise AssertionError("placeholder must not access the provider")

    service = ResearchConsoleSourceService(projection_provider=provider)
    projection = service.missing_projection()

    assert projection.overall_status == "missing"
    assert all(row.status == "missing" for row in projection.gates)
    assert calls == []


def test_cancellation_requested_before_research_console_provider_is_not_degraded() -> None:
    calls: list[str] = []

    def provider(cancel_callback=None) -> None:
        calls.append("called")
        return None

    service = ResearchConsoleSourceService(projection_provider=provider)
    with pytest.raises(ReadOperationCancelled):
        service.inspect(cancel_callback=lambda: True)
    assert calls == []
