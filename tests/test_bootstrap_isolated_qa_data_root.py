from __future__ import annotations

from contextlib import closing
from datetime import date
import hashlib
import json
import sqlite3
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import bootstrap_isolated_qa_data_root as bootstrap


def test_script_cli_help_works_when_launched_outside_repository(tmp_path: Path) -> None:
    script = Path(bootstrap.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "--source-data-root" in result.stdout
    assert "--qa-root-name" in result.stdout


def test_date_parser_rejects_trailing_garbage() -> None:
    for value in ("2026-09-28garbage", "20260928garbage"):
        assert bootstrap._date_text(value) is None


def test_backup_progress_guard_stops_on_restarts_and_total_timeout() -> None:
    class FakeClock:
        current = 0.0

        def monotonic(self) -> float:
            return self.current

        def advance(self, seconds: float) -> None:
            self.current += seconds

    clock = FakeClock()
    stalled = bootstrap._BackupProgressGuard(
        max_duration_seconds=60.0,
        max_stall_seconds=5.0,
        clock=clock.monotonic,
    )
    stalled(sqlite3.SQLITE_OK, 90, 100)
    clock.advance(2.0)
    stalled(sqlite3.SQLITE_BUSY, 100, 100)  # backup restart is not forward progress
    clock.advance(1.0)
    stalled(sqlite3.SQLITE_LOCKED, 100, 101)  # record a changed source page count
    clock.advance(2.1)
    with pytest.raises(bootstrap.BootstrapError, match="淨完成頁數未增加"):
        stalled(sqlite3.SQLITE_BUSY, 100, 101)
    stalled_summary = stalled.summary()
    assert stalled_summary["remaining_increase_count"] == 1
    assert stalled_summary["restart_count"] == 1
    assert stalled_summary["total_change_count"] == 1
    assert stalled_summary["status_counts"] == {"ok": 1, "busy": 2, "locked": 1}
    assert stalled_summary["elapsed_seconds"] >= 5.1
    assert "not a hard wall-clock" in stalled_summary["timeout_enforcement"]

    timed = bootstrap._BackupProgressGuard(
        max_duration_seconds=5.0,
        max_stall_seconds=60.0,
        clock=clock.monotonic,
    )
    timed(sqlite3.SQLITE_OK, 99, 100)
    clock.advance(5.1)
    with pytest.raises(bootstrap.BootstrapError, match="超過總時間上限"):
        timed(sqlite3.SQLITE_OK, 98, 100)


def _create_source(tmp_path: Path, *, latest_date: str = "2026-09-28") -> tuple[Path, sqlite3.Connection]:
    source_root = tmp_path / "formal_source_fixture"
    sqlite_dir = source_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    database = sqlite_dir / "twstock.db"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    for table in bootstrap.REQUIRED_DATE_TABLES:
        connection.execute(f'CREATE TABLE "{table}" ("日期" TEXT NOT NULL, "代碼" TEXT)')
        connection.execute(f'INSERT INTO "{table}" VALUES (?, ?)', (latest_date, "2330"))
    connection.commit()
    return source_root, connection


def _source_sidecars(source_root: Path) -> dict[str, bytes | None]:
    database = source_root / "sqlite" / "twstock.db"
    return {
        name: (Path(str(database) + suffix).read_bytes() if Path(str(database) + suffix).exists() else None)
        for name, suffix in (("db", ""), ("wal", "-wal"), ("shm", "-shm"))
    }


def test_wal_source_is_backed_up_read_only_with_bounded_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    source_before = _source_sidecars(source_root)
    try:
        receipt = bootstrap.bootstrap_isolated_root(
            source_root,
            qa_parent / "run_one",
            as_of_date=date(2026, 9, 29),
        )
        destination = Path(receipt["paths"]["working_db"])
        with sqlite3.connect(destination.resolve().as_uri() + "?mode=ro", uri=True) as reader:
            reader.execute("PRAGMA query_only=ON")
            assert reader.execute("PRAGMA query_only").fetchone() == (1,)
            assert reader.execute('SELECT "代碼" FROM daily_prices').fetchone() == ("2330",)
        assert receipt["status"] == "database_seed_created"
        assert receipt["ready_for_daily_pipeline"] is False
        assert receipt["daily_chain_preflight_complete"] is False
        assert "daily_chain_execution_authorized" not in receipt
        assert receipt["source"]["sqlite_open_mode"] == "mode=ro"
        assert receipt["source"]["query_only"] is True
        assert receipt["source"]["before"]["wal"]["exists"] is True
        assert receipt["source"]["before"]["wal"]["size_bytes"] > 0
        assert receipt["destination"]["quick_check"] == "ok"
        backup_progress = receipt["destination"]["backup_progress"]
        assert backup_progress["pages_per_step"] == bootstrap.BACKUP_PAGES_PER_STEP
        assert backup_progress["progress_callback_count"] > 0
        assert backup_progress["last_remaining_pages"] == 0
        assert backup_progress["last_total_pages"] > 0
        assert backup_progress["restart_count"] == 0
        assert backup_progress["status_counts"]
        assert "callback-only" in backup_progress["timeout_enforcement"]
        assert receipt["destination"]["date_ranges"]["daily_prices"]["max_date"] == "2026-09-28"
        assert receipt["destination"]["hash_is_full_file"] is True
        assert receipt["destination"]["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
        assert receipt["source"]["database_wal_and_journal_observed_fingerprints_stable"] is True
        comparison = receipt["source"]["source_fingerprint_comparison"]
        assert comparison["compared_artifacts"] == ["database", "wal", "journal"]
        assert comparison["compared_fields"] == ["exists", "size_bytes", "mtime_ns", "sha256"]
        assert "do not establish" in comparison["hash_scope"]
        assert receipt["not_bootstrapped"]
        preflight = receipt["operator_preflight_required"]
        assert "separate operator authorization" not in " ".join(preflight)
        assert "same-day calendar/source checks" in preflight[-1]
        assert "external path preflight" in preflight[-1]
        assert json.loads(Path(receipt["paths"]["receipt"]).read_text(encoding="utf-8"))["status"] == "database_seed_created"
        source_after = _source_sidecars(source_root)
        assert source_after["db"] == source_before["db"]
        assert source_after["wal"] == source_before["wal"]

        second = bootstrap.bootstrap_isolated_root(
            source_root,
            qa_parent / "run_two",
            as_of_date=date(2026, 9, 29),
        )
        assert Path(second["paths"]["working_db"]).is_file()
    finally:
        writer.close()


def test_multichunk_wal_backup_reports_completion_and_copies_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    writer.execute("CREATE TABLE backup_payload (payload BLOB NOT NULL)")
    writer.execute("INSERT INTO backup_payload VALUES (zeroblob(100000))")
    writer.commit()
    page_count = int(writer.execute("PRAGMA page_count").fetchone()[0])
    pages_per_step = 4
    assert page_count > pages_per_step * 2

    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    monkeypatch.setattr(bootstrap, "BACKUP_PAGES_PER_STEP", pages_per_step)
    try:
        receipt = bootstrap.bootstrap_isolated_root(
            source_root,
            qa_parent / "multi_chunk_run",
            as_of_date=date(2026, 9, 29),
        )
        progress = receipt["destination"]["backup_progress"]
        assert progress["pages_per_step"] == pages_per_step
        assert progress["last_remaining_pages"] == 0
        assert progress["last_total_pages"] == page_count
        assert progress["progress_callback_count"] > 2
        assert progress["restart_count"] == 0
        assert receipt["source"]["sqlite_open_mode"] == "mode=ro"
        assert receipt["source"]["query_only"] is True
        assert receipt["source"]["before"]["wal"]["exists"] is True

        destination = Path(receipt["paths"]["working_db"])
        assert destination.stat().st_size > 0
        with closing(sqlite3.connect(destination.resolve().as_uri() + "?mode=ro", uri=True)) as reader:
            reader.execute("PRAGMA query_only=ON")
            assert reader.execute("SELECT length(payload) FROM backup_payload").fetchone() == (100000,)
    finally:
        writer.close()


def test_backup_timeout_writes_progress_to_failure_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    monkeypatch.setattr(bootstrap, "BACKUP_MAX_DURATION_SECONDS", 0.0)
    qa_root = qa_parent / "timed_out_run"
    try:
        with pytest.raises(bootstrap.BootstrapError, match="超過總時間上限"):
            bootstrap.bootstrap_isolated_root(
                source_root,
                qa_root,
                as_of_date=date(2026, 9, 29),
            )
        failure = json.loads(
            (qa_root / "bootstrap_failed.json").read_text(encoding="utf-8")
        )
        assert failure["success_receipt_created"] is False
        assert not (qa_root / "bootstrap_receipt.json").exists()
        progress = failure["backup_progress"]
        assert progress["progress_callback_count"] > 0
        assert progress["last_total_pages"] > 0
        assert progress["status_counts"]
        assert "callback-only" in progress["timeout_enforcement"]
    finally:
        writer.close()


def test_existing_destination_and_reparse_parent_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    try:
        qa_parent = tmp_path / "qa"
        qa_parent.mkdir()
        monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
        existing = qa_parent / "already_there"
        existing.mkdir()
        sentinel = existing / "keep.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with pytest.raises(bootstrap.BootstrapError, match="已存在"):
            bootstrap.bootstrap_isolated_root(source_root, existing)
        assert sentinel.read_text(encoding="utf-8") == "preserve"

        outside_parent = tmp_path / "outside_output"
        outside_parent.mkdir()
        with pytest.raises(bootstrap.BootstrapError, match="目的只能是 output/qa"):
            bootstrap.bootstrap_isolated_root(source_root, outside_parent / "run")
        assert not (outside_parent / "run").exists()

        escaped_parent = tmp_path / "redirected_qa"
        escaped_parent.mkdir()
        monkeypatch.setattr(
            bootstrap,
            "_is_reparse_point",
            lambda path: Path(path) == escaped_parent,
        )
        with pytest.raises(bootstrap.BootstrapError, match="symlink/junction"):
            bootstrap.bootstrap_isolated_root(source_root, escaped_parent / "run")
        assert not (escaped_parent / "run").exists()

        monkeypatch.setenv("DATA_ROOT", str(source_root))
        parser = bootstrap._build_parser()
        args = parser.parse_args(["--qa-root-name", "cli_smoke"])
        assert args.source_data_root == source_root
        assert args.qa_root_name == "cli_smoke"
        explicit = parser.parse_args(
            ["--source-data-root", str(source_root), "--qa-root-name", "explicit_smoke"]
        )
        assert explicit.source_data_root == source_root
        assert explicit.qa_root_name == "explicit_smoke"
    finally:
        writer.close()


def test_future_dated_source_leaves_failure_marker_without_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path, latest_date="2099-01-01")
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    qa_root = qa_parent / "future_run"
    try:
        with pytest.raises(bootstrap.BootstrapError, match="未來資料"):
            bootstrap.bootstrap_isolated_root(
                source_root,
                qa_root,
                as_of_date=date(2026, 9, 29),
            )
        assert (qa_root / "bootstrap_failed.json").is_file()
        assert not (qa_root / "bootstrap_receipt.json").exists()
        failure = json.loads((qa_root / "bootstrap_failed.json").read_text(encoding="utf-8"))
        assert failure["status"] == "failed"
        assert failure["success_receipt_created"] is False
    finally:
        writer.close()


def test_mixed_format_future_date_is_detected_after_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    writer.execute('INSERT INTO "daily_prices" VALUES (?, ?)', ("20260930", "2330"))
    writer.commit()
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    qa_root = qa_parent / "mixed_future_run"
    try:
        with pytest.raises(bootstrap.BootstrapError, match="未來資料.*2026-09-30"):
            bootstrap.bootstrap_isolated_root(
                source_root,
                qa_root,
                as_of_date=date(2026, 9, 29),
            )
        assert (qa_root / "bootstrap_failed.json").is_file()
        assert not (qa_root / "bootstrap_receipt.json").exists()
    finally:
        writer.close()


def test_empty_required_table_is_rejected_without_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root, writer = _create_source(tmp_path)
    writer.execute('DELETE FROM "daily_prices"')
    writer.commit()
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    qa_root = qa_parent / "empty_required_table_run"
    try:
        with pytest.raises(bootstrap.BootstrapError, match="沒有日期資料列：daily_prices"):
            bootstrap.bootstrap_isolated_root(
                source_root,
                qa_root,
                as_of_date=date(2026, 9, 29),
            )
        assert (qa_root / "bootstrap_failed.json").is_file()
        assert not (qa_root / "bootstrap_receipt.json").exists()
    finally:
        writer.close()
