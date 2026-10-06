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
    assert "--source-mode" in result.stdout
    assert "--source-snapshot-db" in result.stdout
    assert "--snapshot-receipt" in result.stdout
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


def _create_verified_snapshot_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    latest_date: str = "2026-09-28",
    dual_date_real: bool = False,
) -> tuple[Path, Path, Path, str, str]:
    repo_root = tmp_path / "synthetic_repo"
    relative_snapshot = Path(
        "output/qa/synthetic_upstream/formal_source_snapshot_v2/twstock.db"
    )
    snapshot_db = repo_root / relative_snapshot
    snapshot_db.parent.mkdir(parents=True)
    qa_parent = repo_root / "output" / "qa"
    connection = sqlite3.connect(snapshot_db)
    connection.execute("PRAGMA journal_mode=DELETE")
    for table in bootstrap.REQUIRED_DATE_TABLES:
        if dual_date_real and table in {"daily_prices", "technical_indicators"}:
            connection.execute(
                f'CREATE TABLE "{table}" ("日期" TEXT NOT NULL, "Date" REAL, "代碼" TEXT)'
            )
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?, ?)',
                (latest_date, 20260930.0, "2330"),
            )
        else:
            connection.execute(
                f'CREATE TABLE "{table}" ("日期" TEXT NOT NULL, "代碼" TEXT)'
            )
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?)', (latest_date, "2330")
            )
    connection.commit()
    connection.close()

    inspection_date = date.fromisoformat(latest_date)
    inspected = bootstrap._inspect_snapshot_database(
        snapshot_db, as_of_date=inspection_date
    )
    size_bytes = snapshot_db.stat().st_size
    schema = {
        "logical_size_bytes": size_bytes,
        "page_count": inspected["page_count"],
        "page_size": inspected["page_size"],
        "schema_object_count": inspected["schema_object_count"],
        "schema_sha256": inspected["schema_sha256"],
        "table_count": inspected["table_count"],
        "table_row_counts": inspected["table_row_counts"],
    }
    snapshot_sha256 = bootstrap._full_file_sha256(snapshot_db)
    formal_source = r"D:\synthetic-formal-data\sqlite\twstock.db"
    before = {
        "main": {
            "path": formal_source,
            "exists": True,
            "is_regular_file": True,
            "is_reparse_point": False,
            "is_symlink": False,
            "size_bytes": size_bytes,
            "sha256": "a" * 64,
        },
        "wal": {
            "path": formal_source + "-wal",
            "exists": True,
            "is_regular_file": True,
            "is_reparse_point": False,
            "is_symlink": False,
            "size_bytes": 0,
            "sha256": hashlib.sha256(b"").hexdigest(),
        },
        "shm": {
            "path": formal_source + "-shm",
            "exists": True,
            "is_regular_file": True,
            "is_reparse_point": False,
            "is_symlink": False,
            "size_bytes": 32768,
            "sha256": "b" * 64,
        },
    }
    upstream = {
        "backup_pages_per_step": -1,
        "completed_at": "2026-09-28T02:00:00+00:00",
        "method": "sqlite3.Connection.backup from mode=ro source with query_only=ON",
        "schema_version": bootstrap.SNAPSHOT_SCHEMA_VERSION,
        "snapshot_data_version_checks": [1, 1, 1],
        "snapshot_data_version_stable": True,
        "snapshot_integrity_check": ["ok"],
        "snapshot_journal_mode": "delete",
        "snapshot_path": str(snapshot_db.resolve()),
        "snapshot_schema": schema,
        "snapshot_scope": "repo-ignored QA only; no formal-data writes",
        "snapshot_sha256": snapshot_sha256,
        "source_after": before,
        "source_before": before,
        "source_confirmation": formal_source,
        "source_path": formal_source,
        "source_schema": schema,
        "source_unchanged": True,
        "started_at": "2026-09-28T01:00:00+00:00",
        "status": "complete",
    }
    receipt = snapshot_db.parent / "snapshot_receipt.json"
    receipt_bytes = (json.dumps(upstream, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    receipt.write_bytes(receipt_bytes)

    monkeypatch.setattr(bootstrap, "REPO_ROOT", repo_root)
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    monkeypatch.setattr(bootstrap, "SNAPSHOT_RELATIVE_PATH", relative_snapshot)
    monkeypatch.setattr(bootstrap, "SNAPSHOT_SHA256", snapshot_sha256)
    monkeypatch.setattr(bootstrap, "SNAPSHOT_RECEIPT_SHA256", hashlib.sha256(receipt_bytes).hexdigest())
    monkeypatch.setattr(bootstrap, "SNAPSHOT_SCHEMA_SHA256", schema["schema_sha256"])
    monkeypatch.setattr(bootstrap, "SNAPSHOT_SIZE_BYTES", size_bytes)
    monkeypatch.setattr(bootstrap, "SNAPSHOT_SCHEMA_OBJECT_COUNT", schema["schema_object_count"])
    monkeypatch.setattr(bootstrap, "SNAPSHOT_TABLE_COUNT", schema["table_count"])
    monkeypatch.setattr(bootstrap, "SNAPSHOT_PAGE_COUNT", schema["page_count"])
    monkeypatch.setattr(bootstrap, "SNAPSHOT_PAGE_SIZE", schema["page_size"])
    return snapshot_db, receipt, qa_parent, snapshot_sha256, hashlib.sha256(receipt_bytes).hexdigest()


def test_verified_snapshot_mode_copies_pinned_bytes_without_opening_formal_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_db, upstream_receipt, qa_parent, snapshot_sha256, receipt_sha256 = (
        _create_verified_snapshot_fixture(
            tmp_path, monkeypatch, dual_date_real=True
        )
    )
    opened_databases: list[Path] = []
    original_connect = bootstrap._connect_read_only

    def track_read_only(path: Path) -> sqlite3.Connection:
        opened_databases.append(Path(path).resolve())
        return original_connect(path)

    monkeypatch.setattr(bootstrap, "_connect_read_only", track_read_only)
    result = bootstrap.bootstrap_from_verified_qa_snapshot(
        snapshot_db, upstream_receipt, qa_parent / "verified_snapshot_seed"
    )
    working_db = Path(result["paths"]["working_db"])
    assert result["source_mode"] == "verified_qa_snapshot"
    assert result["ready_for_daily_pipeline"] is False
    assert result["daily_chain_preflight_complete"] is False
    assert result["research_use_only"] is True
    assert result["official_point_in_time_eligibility"] == "not_established"
    assert "guarded_daily_tables_exclude_date" not in result
    assert result["date_guard_scope"]["tables"] == list(bootstrap.REQUIRED_DATE_TABLES)
    assert result["date_guard_scope"]["claim"].startswith(
        "only each listed date_ranges entry's selected date_column max_date"
    )
    assert result["date_guard_scope"]["other_tables_date_scanned"] is False
    assert result["date_guard_scope"]["unscanned_date_candidate_columns"]["daily_prices"] == [
        "Date"
    ]
    assert result["date_guard_scope"]["unscanned_candidate_columns_parsed_or_normalized"] is False
    assert result["lookahead_self_check"]["guarded_tables"] == list(
        bootstrap.REQUIRED_DATE_TABLES
    )
    assert result["lookahead_self_check"]["status"] == "partial"
    assert result["lookahead_self_check"]["all_reported_date_range_max_dates_at_or_before_2026_09_28"] is True
    assert result["lookahead_self_check"]["full_database_future_date_absence_established"] is False
    assert "2026_09_29_data_included_in_guarded_tables" not in result["lookahead_self_check"]
    assert result["lookahead_self_check"]["other_tables_date_scanned"] is False
    assert result["lineage"]["upstream_receipt_sha256"] == receipt_sha256
    assert result["lineage"]["snapshot_sha256"] == snapshot_sha256
    assert result["lineage"]["formal_source_path_access"]["receipt_d_paths_directly_opened_or_statted"] is False
    assert "not bound to OS file handles" in result["source"]["filesystem_race_limitation"]
    assert result["destination"]["quick_check"] == "ok"
    assert result["destination"]["date_ranges"]["daily_prices"]["max_date"] == "2026-09-28"
    assert result["destination"]["date_ranges"]["daily_prices"]["date_column"] == "日期"
    assert result["destination"]["date_ranges"]["daily_prices"]["unscanned_date_columns"] == [
        "Date"
    ]
    with closing(
        sqlite3.connect(working_db.resolve().as_uri() + "?mode=ro", uri=True)
    ) as reader:
        reader.execute("PRAGMA query_only=ON")
        assert reader.execute('SELECT "Date" FROM daily_prices').fetchone() == (
            20260930.0,
        )
    assert bootstrap._full_file_sha256(working_db) == snapshot_sha256
    assert opened_databases == [working_db.resolve(), working_db.resolve()]
    assert not (qa_parent / "verified_snapshot_seed" / "bootstrap_failed.json").exists()


def test_verified_snapshot_rejects_receipt_forgery_and_writes_failure_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_db, upstream_receipt, qa_parent, _, _ = _create_verified_snapshot_fixture(
        tmp_path, monkeypatch
    )
    upstream_receipt.write_bytes(upstream_receipt.read_bytes() + b" ")
    qa_root = qa_parent / "forged_receipt_seed"
    with pytest.raises(bootstrap.BootstrapError, match="receipt SHA"):
        bootstrap.bootstrap_from_verified_qa_snapshot(
            snapshot_db, upstream_receipt, qa_root
        )
    failure = json.loads((qa_root / "bootstrap_failed.json").read_text(encoding="utf-8"))
    assert failure["success_receipt_created"] is False
    assert not (qa_root / "bootstrap_receipt.json").exists()


def test_target_path_guard_detects_reparse_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qa_parent = tmp_path / "qa"
    qa_parent.mkdir()
    target_root = qa_parent / "guarded_run"
    data_root = target_root / "data"
    sqlite_dir = data_root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "QA_PARENT", qa_parent)
    original_is_reparse = bootstrap._is_reparse_point
    monkeypatch.setattr(
        bootstrap,
        "_is_reparse_point",
        lambda path: Path(path) == data_root or original_is_reparse(Path(path)),
    )
    with pytest.raises(bootstrap.BootstrapError, match="symlink/junction"):
        bootstrap._assert_target_path_in_qa(
            target_root, sqlite_dir / "twstock.db"
        )


def test_verified_snapshot_rejects_data_after_research_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_db, upstream_receipt, qa_parent, _, _ = _create_verified_snapshot_fixture(
        tmp_path, monkeypatch, latest_date="2026-09-29"
    )
    qa_root = qa_parent / "future_snapshot_seed"
    with pytest.raises(bootstrap.BootstrapError, match="未來資料"):
        bootstrap.bootstrap_from_verified_qa_snapshot(
            snapshot_db, upstream_receipt, qa_root
        )
    failure = json.loads((qa_root / "bootstrap_failed.json").read_text(encoding="utf-8"))
    assert failure["success_receipt_created"] is False
    assert not (qa_root / "bootstrap_receipt.json").exists()


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
        assert args.source_mode == "formal-data-root"
        assert args.source_data_root is None
        assert args.qa_root_name == "cli_smoke"
        explicit = parser.parse_args(
            ["--source-data-root", str(source_root), "--qa-root-name", "explicit_smoke"]
        )
        assert explicit.source_data_root == source_root
        assert explicit.qa_root_name == "explicit_smoke"
        alternate = parser.parse_args(
            [
                "--source-mode",
                "verified-qa-snapshot",
                "--source-snapshot-db",
                str(source_root / "sqlite" / "twstock.db"),
                "--snapshot-receipt",
                str(source_root / "snapshot_receipt.json"),
                "--qa-root-name",
                "alternate_smoke",
            ]
        )
        assert alternate.source_mode == "verified-qa-snapshot"
        assert alternate.source_snapshot_db == source_root / "sqlite" / "twstock.db"
        assert alternate.snapshot_receipt == source_root / "snapshot_receipt.json"
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
