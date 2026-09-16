import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from data_module.db_manager import DBManager


def test_writer_waits_for_competing_transaction_and_rolls_back(tmp_path):
    path = tmp_path / "contention.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    manager = object.__new__(DBManager)
    manager.db_path = path
    manager.logger = logging.getLogger(__name__)
    entered = threading.Event()
    holder = sqlite3.connect(path)
    holder.execute("BEGIN IMMEDIATE")

    def write():
        with manager.connect() as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            entered.set()
            conn.execute("INSERT INTO items VALUES (1)")

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(write)
            assert entered.wait(5)
            holder.rollback()
            future.result(timeout=5)
    finally:
        holder.close()
    try:
        with manager.connect() as conn:
            conn.execute("INSERT INTO items VALUES (2)")
            raise ValueError("rollback probe")
    except ValueError:
        pass
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id FROM items").fetchall() == [(1,)]
