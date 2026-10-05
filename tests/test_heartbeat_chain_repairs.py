"""使用真實子程序及 SQLite 驗證每日鏈路修正，不接觸正式資料。"""
from pathlib import Path
import json
import os
import sqlite3
import sys

import pytest

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation, heavy_chain_lock_path,
    release_heavy_chain_reservation,
)
from scripts.scheduled import current_stock_research_cycle as cycle
from scripts.scheduled import run_scheduled_decision_evidence_capture as capture


@pytest.mark.parametrize("forged", [False, True])
def test_real_evidence_child_requires_valid_parent_lease(tmp_path: Path, forged: bool) -> None:
    root = tmp_path / "release_v4"
    lock_path = heavy_chain_lock_path(root)
    reservation = acquire_heavy_chain_reservation(lock_path)
    assert reservation is not None
    child = tmp_path / "capture_evidence_events.py"
    child.write_text(
        "import sys, json, os\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(capture.REPO_ROOT)!r})\n"
        "from types import SimpleNamespace\n"
        "from scripts import capture_evidence_events as cli\n"
        "from data_module.ml_storage_capacity import acquire_heavy_chain_reservation\n"
        f"lock_path = Path({str(lock_path)!r})\n"
        f"cli._config_from_args = lambda args: SimpleNamespace(db_file=Path({str(tmp_path / 'source.db')!r}))\n"
        "cli.TWStockConfig = lambda: object()\n"
        f"cli.resolve_canonical_evidence_release_root = lambda **kw: Path({str(root)!r})\n"
        "def run(*args, **kwargs):\n"
        "    assert acquire_heavy_chain_reservation(lock_path) is None\n"
        "    print(json.dumps({'status': 'verified_parent_lease'}))\n"
        "    return 0\n"
        "cli._run_capture = run\n"
        + ("os.environ['BALDR_ML_HEAVY_CHAIN_RESERVATION_HELD'] = '1'\n" if forged else "")
        + "sys.exit(cli.main(['--source', 'all', '--confirm']))\n", encoding="utf-8",
    )
    token = capture._CHILD_RESERVATION.set(reservation)
    try:
        result = capture._run_json_cli([sys.executable, str(child)], timeout_seconds=15)
        if forged:
            assert result.returncode != 0
        else:
            assert result.returncode == 0
            assert result.payload == {"status": "verified_parent_lease"}
        assert acquire_heavy_chain_reservation(lock_path) is None
    finally:
        capture._CHILD_RESERVATION.reset(token)
        release_heavy_chain_reservation(reservation)
    next_owner = acquire_heavy_chain_reservation(lock_path)
    assert next_owner is not None
    release_heavy_chain_reservation(next_owner)


@pytest.mark.parametrize("change", ["empty_wal", "mtime", "content"])
def test_snapshot_keeps_content_guard_without_empty_wal_false_alarm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE sample (value INTEGER)")
        connection.execute("INSERT INTO sample VALUES (1)")
        connection.commit()
    connection.close()
    if change == "empty_wal":
        source.with_name(source.name + "-wal").write_bytes(b"")
    original_pin = cycle._pin_regular_file
    calls = 0

    def pin(path, *, label):
        nonlocal calls
        if Path(path) == source:
            calls += 1
            if calls == 2:
                if change == "mtime":
                    stat = source.stat()
                    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
                elif change == "content":
                    writer = sqlite3.connect(source)
                    writer.execute("UPDATE sample SET value=2")
                    writer.commit()
                    writer.close()
        return original_pin(path, label=label)

    monkeypatch.setattr(cycle, "_pin_regular_file", pin)
    monkeypatch.setattr(cycle, "_source_namespace_pins", lambda _path: [])
    kwargs = dict(source_database=source, snapshot_database=tmp_path / "copy.db",
                  receipt_path=tmp_path / "receipt.json")
    if change == "content":
        with pytest.raises(cycle._WaitingForSource, match="database"):
            cycle._create_consistent_snapshot(**kwargs)
        assert not (tmp_path / "receipt.json").exists()
        failure = json.loads((tmp_path / "snapshot_failure.json").read_text())
        assert failure["source_database_before"]["sha256"] != failure["source_database_after"]["sha256"]
        assert failure["formal_credit"] is False
    else:
        result = cycle._create_consistent_snapshot(**kwargs)
        assert json.loads(Path(result["snapshot_receipt_path"]).read_text())["source_and_revision_bytes_unchanged"]
        with sqlite3.connect(tmp_path / "copy.db") as copy:
            assert copy.execute("SELECT value FROM sample").fetchone() == (1,)
