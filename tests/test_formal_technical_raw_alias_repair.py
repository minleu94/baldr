"""正式六個 raw alias 維護工具的隔離端到端測試。"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from data_module import formal_technical_raw_alias_repair as repair


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")


def _table_hash_like_publisher(connection: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
    digest = hashlib.sha256(_encoded(columns))
    cursor = connection.execute(f'SELECT * FROM "{table}" ORDER BY "證券代號", "日期"')
    while rows := cursor.fetchmany(5000):
        digest.update(_encoded(rows))
    return digest.hexdigest()


def _canonical_rows(
    *,
    include_extended_symbol: bool = False,
    include_second_extended_symbol: bool = False,
) -> list[tuple[str, str, object, object, object, object, object, object]]:
    rows = [
        ("20260520", "0050", 100.0, 15, 101.0, 18, None, 2.5),
        ("20260521", "0050", None, None, 102.0, 20, 13.1, 1.0),
        ("20260520", "2330", 1500.0, 30, 1501.0, 32, 19.2, 5.0),
        ("20260521", "2330", 1502.0, 31, 1503.0, 33, 19.3, 2.0),
    ]
    if include_extended_symbol:
        rows.extend([
            ("20260520", "1101B", 44.0, 8, 44.5, 9, 12.3, 0.5),
            ("20260521", "1101B", 44.5, 9, 45.0, 10, 12.4, 0.5),
        ])
    if include_second_extended_symbol:
        rows.extend([
            ("20260520", "2887Z1", 14.0, 8, 14.5, 9, 12.3, 0.5),
            ("20260521", "2887Z1", 14.5, 9, 15.0, 10, 12.4, 0.5),
        ])
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _fixture(
    tmp_path: Path,
    *,
    omit_aggregate_key: bool = False,
    include_extended_symbol: bool = False,
    include_second_extended_symbol: bool = False,
    alias_override_for_2330: tuple[object, ...] | None = None,
) -> tuple[Path, Path, Path, dict[str, str]]:
    canonical_rows = _canonical_rows(
        include_extended_symbol=include_extended_symbol,
        include_second_extended_symbol=include_second_extended_symbol,
    )
    if alias_override_for_2330 is not None:
        if len(alias_override_for_2330) != len(repair.ALIASES):
            raise ValueError("測試 alias override 必須包含六個值")
        canonical_rows = [
            (row[0], row[1], *alias_override_for_2330)
            if row[0] == "20260520" and row[1] == "2330"
            else row
            for row in canonical_rows
        ]
    root = tmp_path / "formal-root"
    db_dir = root / "sqlite"
    technical_dir = root / "technical_analysis"
    meta_dir = root / "meta_data"
    db_dir.mkdir(parents=True)
    technical_dir.mkdir()
    meta_dir.mkdir()
    technical_receipt_dir = root / repair.SOURCE_RECEIPT_ROOT / "20260923_run02"
    (technical_receipt_dir / "stage" / "staged" / "technical_analysis").mkdir(parents=True)
    (technical_receipt_dir / "stage" / "staged" / "meta_data").mkdir(parents=True)
    source_db = technical_receipt_dir / "source.sqlite"
    live_db = db_dir / "twstock.db"

    with sqlite3.connect(source_db) as connection:
        connection.execute(
            'CREATE TABLE daily_prices '
            '("證券代號" TEXT NOT NULL,"日期" TEXT NOT NULL,"最後揭示買價" REAL,"最後揭示買量" INTEGER,'
            '"最後揭示賣價" REAL,"最後揭示賣量" INTEGER,"本益比" REAL,"漲跌價差" REAL,'
            '"收盤價" REAL,PRIMARY KEY("證券代號","日期"))'
        )
        connection.execute(
            'CREATE TABLE technical_indicators '
            '("證券代號" TEXT NOT NULL,"日期" TEXT NOT NULL,"最後揭示買價" REAL,"最後揭示買量" INTEGER,'
            '"最後揭示賣價" REAL,"最後揭示賣量" INTEGER,"本益比" REAL,"漲跌價差" REAL,'
            '"MA5" REAL,PRIMARY KEY("證券代號","日期"))'
        )
        connection.execute('CREATE INDEX idx_daily_date ON daily_prices("日期")')
        connection.execute('CREATE INDEX idx_technical_date ON technical_indicators("日期")')
        for row in canonical_rows:
            day, symbol, bid, bid_volume, ask, ask_volume, pe, change = row
            connection.execute(
                'INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?,?,?)',
                (symbol, day, bid, bid_volume, ask, ask_volume, pe, change, 50.0),
            )
            # 技術 cache 故意留有過去全表補值／舊值。
            connection.execute(
                'INSERT INTO technical_indicators VALUES (?,?,?,?,?,?,?,?,?)',
                (symbol, day, 999.0, 999, 998.0, 998, 99.9, 88.8, 42.0),
            )
    shutil.copyfile(source_db, live_db)

    fields = ["日期", "證券代號", *repair.ALIASES, "MA5", "註記"]
    csv_by_symbol: dict[str, list[dict[str, str]]] = {
        symbol: [] for symbol in sorted({row[1] for row in canonical_rows})
    }
    aggregate_rows: list[dict[str, str]] = []
    for day, symbol, *_ in sorted(canonical_rows, key=lambda item: (item[0], item[1])):
        row = {
            "日期": f"{day[:4]}-{day[4:6]}-{day[6:]}",
            "證券代號": symbol,
            "最後揭示買價": "999",
            "最後揭示買量": "999",
            "最後揭示賣價": "998",
            "最後揭示賣量": "998",
            "本益比": "99.9",
            "漲跌價差": "88.8",
            "MA5": "42.0",
            "註記": f"keep-{symbol}-{day}",
        }
        csv_by_symbol[symbol].append(row)
        aggregate_rows.append(row.copy())
    if omit_aggregate_key:
        aggregate_rows.pop()
    target_paths = {
        symbol: technical_dir / f"{symbol}_indicators.csv" for symbol in csv_by_symbol
    }
    for symbol, rows in csv_by_symbol.items():
        _write_csv(target_paths[symbol], rows, fields)
    aggregate_path = meta_dir / "all_stocks_data.csv"
    _write_csv(aggregate_path, aggregate_rows, fields)

    stage_files = []
    for target in [*target_paths.values(), aggregate_path]:
        relative = Path("staged") / ("meta_data" if target == aggregate_path else "technical_analysis") / target.name
        staged_path = technical_receipt_dir / "stage" / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, staged_path)
        after_sha = repair._file_hash(target)
        stage_files.append({
            "target_path": str(target.resolve()),
            "staged_path": str(staged_path.resolve()),
            "before_sha256": after_sha,
            "after_sha256": after_sha,
            "row_count_after": len(_csv_rows(target)[1]),
        })
    with repair._readonly(source_db) as connection:
        daily_hash = repair._table_hash(connection, "daily_prices")
        technical_hash = repair._table_hash(connection, "technical_indicators")
    source_sha = repair._file_hash(source_db)
    source_json = {
        "schema_version": "formal-technical-repair.v1",
        "root": str(root.resolve()),
        "source_db": str(source_db.resolve()),
        "source_sha256": source_sha,
        "daily_before_hash": daily_hash,
        "technical_before_hash": technical_hash,
        "prepared_at": "2026-09-23T00:00:00+00:00",
    }
    (technical_receipt_dir / "source.json").write_bytes(repair._json_bytes(source_json))
    technical_manifest = {
        "schema_version": repair.TECHNICAL_STAGE_SCHEMA,
        "source_db": str(source_db.resolve()),
        "source_sha256": source_sha,
        "rows": len(canonical_rows),
        "exclusion_evidence_identities": [],
        "files": stage_files,
    }
    manifest_path = technical_receipt_dir / "stage" / "manifest.json"
    manifest_path.write_bytes(repair._json_bytes(technical_manifest))
    manifest_sha = repair._file_hash(manifest_path)
    applied_files = [
        {"target_path": item["target_path"], "after_sha256": item["after_sha256"], "backup": "csv_before/test.csv"}
        for item in stage_files
    ]
    applied_receipt = {
        "state": "applied",
        "manifest_sha256": manifest_sha,
        "source_db": str(source_db.resolve()),
        "source_sha256": source_sha,
        "technical_after_hash": technical_hash,
        "files": applied_files,
        "completed_at": "2026-09-23T00:01:00+00:00",
    }
    receipt_path = technical_receipt_dir / "receipt.json"
    receipt_path.write_bytes(repair._json_bytes(applied_receipt))
    (technical_receipt_dir / "journal.json").write_bytes(repair._json_bytes(applied_receipt))
    new_receipt = root / repair.RECEIPT_ROOT / "run01"
    (root / repair.RECEIPT_ROOT).mkdir(parents=True)
    original_hashes = {str(path): repair._file_hash(path) for path in [live_db, *target_paths.values(), aggregate_path]}
    return root, technical_receipt_dir, new_receipt, original_hashes


def _run_to_audit(root: Path, technical_receipt: Path, new_receipt: Path) -> tuple[dict[str, object], str]:
    repair.prepare(root, technical_receipt, new_receipt)
    manifest = repair.stage(new_receipt)
    manifest_path = new_receipt / "stage" / "manifest.json"
    manifest_sha = repair._file_hash(manifest_path)
    audited = repair.audit(new_receipt, manifest_sha)
    assert audited["state"] == "passed"
    return manifest, manifest_sha


def test_prepare_stage_audit_apply_readback_and_rollback_are_end_to_end(tmp_path: Path) -> None:
    root, technical_receipt, new_receipt, original_hashes = _fixture(tmp_path)
    manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    assert manifest["canonical_rows"] == 4
    assert manifest["database_rows_checked"] == 4
    assert manifest["csv_rows_checked"] == 8
    assert manifest["target_file_count"] == 3
    assert manifest["database_field_deltas"]["最後揭示買量"]["canonical_null_existing_filled"] == 1
    assert manifest["database_field_deltas"]["本益比"]["both_filled_different"] == 3
    audit_receipt = repair._read_sealed(new_receipt / "audit.json")
    assert audit_receipt["source_daily_rows_checked"] == 4
    assert audit_receipt["all_staged_aliases_equal_authoritative_daily"] is True
    assert audit_receipt["all_non_target_csv_values_preserved"] is True

    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        original_ma5 = list(connection.execute(
            "SELECT MA5 FROM technical_indicators ORDER BY 證券代號,日期"
        ))
    applied = repair.apply(new_receipt, manifest_sha)
    assert applied["state"] == "applied"
    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        actual = list(connection.execute(
            'SELECT 證券代號,日期,"最後揭示買價","最後揭示買量","最後揭示賣價","最後揭示賣量",本益比,漲跌價差,MA5 '
            'FROM technical_indicators ORDER BY 證券代號,日期'
        ))
        expected_aliases = list(connection.execute(
            'SELECT 證券代號,日期,"最後揭示買價","最後揭示買量","最後揭示賣價","最後揭示賣量",本益比,漲跌價差 '
            'FROM daily_prices ORDER BY 證券代號,日期'
        ))
    assert [row[:8] for row in actual] == expected_aliases
    assert [row[8:] for row in actual] == original_ma5
    for target in [root / "technical_analysis" / "0050_indicators.csv", root / "technical_analysis" / "2330_indicators.csv", root / "meta_data" / "all_stocks_data.csv"]:
        fields, rows = _csv_rows(target)
        assert fields[-2:] == ["MA5", "註記"]
        assert all(row["MA5"] == "42.0" for row in rows)
        assert all(row["最後揭示買量"] != "999" for row in rows)
    marker = repair.load_applied_raw_alias_receipt(root / "sqlite" / "twstock.db")
    assert marker is not None and marker["state"] == "applied"
    assert marker["canonical_rows"] == 4
    assert marker["rollback_csv_backups_verified"] is True

    rolled = repair.recover(new_receipt, rollback=True, expected_manifest_hash=manifest_sha)
    assert rolled["state"] == "rolled_back"
    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == manifest["database_before"]
    for target in [root / "technical_analysis" / "0050_indicators.csv", root / "technical_analysis" / "2330_indicators.csv", root / "meta_data" / "all_stocks_data.csv"]:
        assert repair._file_hash(target) == original_hashes[str(target)]
    assert repair.load_applied_raw_alias_receipt(root / "sqlite" / "twstock.db") is None


def test_resume_completes_after_database_commit_and_partial_csv_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    _manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    original_publish = repair._publish_csvs
    interrupted = False

    def publish_one_then_interrupt(receipt_dir: Path, manifest: dict[str, object], journal: dict[str, object], *, after: bool) -> None:
        nonlocal interrupted
        if after and not interrupted:
            interrupted = True
            partial_manifest = dict(manifest)
            partial_manifest["csv_targets"] = manifest["csv_targets"][:1]
            partial_journal = dict(journal)
            partial_journal["files"] = journal["files"][:1]
            original_publish(receipt_dir, partial_manifest, partial_journal, after=True)
            raise OSError("測試用：第一個 CSV 發布後中斷")
        original_publish(receipt_dir, manifest, journal, after=after)

    monkeypatch.setattr(repair, "_publish_csvs", publish_one_then_interrupt)
    with pytest.raises(OSError, match="測試用"):
        repair.apply(new_receipt, manifest_sha)
    journal = repair._read_sealed(new_receipt / "journal.json")
    assert journal["state"] == "pending"
    assert journal["database_after"]["rows"] == 4
    monkeypatch.setattr(repair, "_publish_csvs", original_publish)
    resumed = repair.recover(new_receipt, rollback=False, expected_manifest_hash=manifest_sha)
    assert resumed["state"] == "applied"
    assert repair._read_sealed(new_receipt / "receipt.json")["canonical_rows"] == 4


def test_resume_preflights_last_backup_before_any_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    _manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    original_publish = repair._publish_csvs

    def publish_one_then_interrupt(receipt_dir: Path, manifest: dict[str, object], journal: dict[str, object], *, after: bool) -> None:
        if after:
            partial_manifest = dict(manifest)
            partial_manifest["csv_targets"] = manifest["csv_targets"][:1]
            partial_journal = dict(journal)
            partial_journal["files"] = journal["files"][:1]
            original_publish(receipt_dir, partial_manifest, partial_journal, after=True)
            raise OSError("測試用：第一個 CSV 發布後中斷")
        original_publish(receipt_dir, manifest, journal, after=after)

    monkeypatch.setattr(repair, "_publish_csvs", publish_one_then_interrupt)
    with pytest.raises(OSError, match="測試用"):
        repair.apply(new_receipt, manifest_sha)
    monkeypatch.setattr(repair, "_publish_csvs", original_publish)

    manifest = repair._read_sealed(new_receipt / "stage" / "manifest.json")
    journal = repair._read_sealed(journal_path := new_receipt / "journal.json")
    journal_sha = repair._file_hash(journal_path)
    targets = [Path(item["target_path"]) for item in manifest["csv_targets"]]
    target_hashes = {str(path): repair._file_hash(path) for path in targets}
    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        database_after = repair._table_fingerprint(connection, "technical_indicators")
    last_backup = new_receipt / journal["files"][-1]["backup_relative_path"]
    last_backup.write_bytes(last_backup.read_bytes() + b"\n")
    corrupt_backup_hash = repair._file_hash(last_backup)

    with pytest.raises(repair.RawAliasRepairError, match="backup hash 不符"):
        repair.recover(new_receipt, rollback=False, expected_manifest_hash=manifest_sha)

    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == database_after
    assert repair._file_hash(journal_path) == journal_sha
    assert repair._file_hash(last_backup) == corrupt_backup_hash
    for target in targets:
        assert repair._file_hash(target) == target_hashes[str(target)]


def test_second_sql_batch_failure_rolls_back_without_changing_db_or_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, technical_receipt, new_receipt, original_hashes = _fixture(tmp_path)
    # 讓第二批 UPDATE 發生故障；第一批也必須隨 SQLite transaction 一起回滾。
    with sqlite3.connect(root / "sqlite" / "twstock.db") as connection:
        connection.execute(
            "CREATE TRIGGER fail_second_symbol_alias_update "
            'BEFORE UPDATE OF "最後揭示買價" ON technical_indicators '
            "WHEN OLD.證券代號='2330' BEGIN SELECT RAISE(ABORT,'fixture fault'); END"
        )
    original_hashes[str(root / "sqlite" / "twstock.db")] = repair._file_hash(root / "sqlite" / "twstock.db")
    _manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    monkeypatch.setattr(repair, "_CHUNK_ROWS", 2)
    with pytest.raises(sqlite3.IntegrityError, match="fixture fault"):
        repair.apply(new_receipt, manifest_sha)
    assert repair._file_hash(root / "sqlite" / "twstock.db") == original_hashes[str(root / "sqlite" / "twstock.db")]
    assert repair._read_sealed(new_receipt / "journal.json")["state"] == "pending"
    for target in [root / "technical_analysis" / "0050_indicators.csv", root / "technical_analysis" / "2330_indicators.csv", root / "meta_data" / "all_stocks_data.csv"]:
        assert repair._file_hash(target) == original_hashes[str(target)]
    rolled = repair.recover(new_receipt, rollback=True, expected_manifest_hash=manifest_sha)
    assert rolled["state"] == "rolled_back"


def test_rejects_unapplied_receipt_and_csv_key_gap_before_publication(tmp_path: Path) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path, omit_aggregate_key=True)
    receipt_path = technical_receipt / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["state"] = "pending"
    encoded = repair._json_bytes(receipt)
    receipt_path.write_bytes(encoded)
    (technical_receipt / "journal.json").write_bytes(encoded)
    with pytest.raises(repair.RawAliasRepairError, match="applied"):
        repair.prepare(root, technical_receipt, new_receipt)
    assert not new_receipt.exists()

    # 還原可信 applied marker 後，缺少 aggregate source key 的 CSV 在 stage 被拒絕。
    receipt["state"] = "applied"
    (technical_receipt / "receipt.json").write_bytes(repair._json_bytes(receipt))
    (technical_receipt / "journal.json").write_bytes(repair._json_bytes(receipt))
    repair.prepare(root, technical_receipt, new_receipt)
    with pytest.raises(repair.RawAliasRepairError, match="key 集合不同|遺漏"):
        repair.stage(new_receipt)
    assert not (new_receipt / "stage").exists()


def test_daily_source_drift_blocks_rollback_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    _manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    original_publish = repair._publish_csvs

    def interrupt_after_db(receipt_dir: Path, manifest: dict[str, object], journal: dict[str, object], *, after: bool) -> None:
        if after:
            raise OSError("測試用：DB 已 commit，CSV 尚未發布")
        original_publish(receipt_dir, manifest, journal, after=after)

    monkeypatch.setattr(repair, "_publish_csvs", interrupt_after_db)
    with pytest.raises(OSError, match="測試用"):
        repair.apply(new_receipt, manifest_sha)
    monkeypatch.setattr(repair, "_publish_csvs", original_publish)
    with sqlite3.connect(root / "sqlite" / "twstock.db") as connection:
        connection.execute("UPDATE daily_prices SET 收盤價=51 WHERE 證券代號='0050'")
    with pytest.raises(repair.RawAliasRepairError, match="daily_prices 已漂移"):
        repair.recover(new_receipt, rollback=False, expected_manifest_hash=manifest_sha)
    with pytest.raises(repair.RawAliasRepairError, match="daily_prices 已漂移"):
        repair.recover(new_receipt, rollback=True, expected_manifest_hash=manifest_sha)


def test_rollback_preflights_last_csv_before_changing_database_or_any_file(tmp_path: Path) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    _manifest, manifest_sha = _run_to_audit(root, technical_receipt, new_receipt)
    assert repair.apply(new_receipt, manifest_sha)["state"] == "applied"
    manifest = repair._read_sealed(new_receipt / "stage" / "manifest.json")
    journal_path = new_receipt / "journal.json"
    journal_sha = repair._file_hash(journal_path)
    targets = [Path(item["target_path"]) for item in manifest["csv_targets"]]
    before_drift_hashes = {str(path): repair._file_hash(path) for path in targets}
    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        before_drift_database = repair._table_fingerprint(connection, "technical_indicators")

    last_target = targets[-1]
    last_target.write_bytes(last_target.read_bytes() + b"\n")
    drift_hash = repair._file_hash(last_target)
    with pytest.raises(repair.RawAliasRepairError, match="CSV 在 recovery 前已漂移"):
        repair.recover(new_receipt, rollback=True, expected_manifest_hash=manifest_sha)

    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before_drift_database
    assert repair._file_hash(journal_path) == journal_sha
    for target in targets[:-1]:
        assert repair._file_hash(target) == before_drift_hashes[str(target)]
    assert repair._file_hash(last_target) == drift_hash


def test_writer_guard_accepts_canonical_rows_rejects_stale_or_missing_and_allows_unprotected_new_key(tmp_path: Path) -> None:
    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    with repair._readonly(database_path) as connection:
        technical_rows = list(connection.execute(
            'SELECT 證券代號,日期,"最後揭示買價","最後揭示買量","最後揭示賣價","最後揭示賣量",本益比,漲跌價差 '
            'FROM daily_prices ORDER BY 證券代號,日期'
        ))
    columns = ["證券代號", "日期", *repair.ALIASES]
    records = [dict(zip(columns, row, strict=True)) for row in technical_rows]

    # 沒有 applied marker 時維持既有一般寫入行為。
    repair.validate_raw_alias_replacement(database_path, records, replace_all=True)
    _run_to_audit(root, technical_receipt, new_receipt)
    manifest = repair._read_sealed(new_receipt / "stage" / "manifest.json")
    repair.apply(new_receipt, repair._file_hash(new_receipt / "stage" / "manifest.json"))

    repair.validate_raw_alias_replacement(database_path, records, replace_all=True)
    stale = [dict(row) for row in records]
    stale[0]["最後揭示買價"] = 999
    with pytest.raises(repair.RawAliasRepairError, match="舊來源會覆寫"):
        repair.validate_raw_alias_replacement(database_path, stale, replace_all=True)
    with pytest.raises(repair.RawAliasRepairError, match="缺少 [0-9]+ 個受保護 key"):
        repair.validate_raw_alias_replacement(database_path, records[:-1], replace_all=True)
    repair.validate_raw_alias_replacement(
        database_path,
        [{"日期": "20260522", "證券代號": "0050"}],
    )

    # Source 檔 identity 變更即 fail closed，不以新內容代替已核准來源。
    source_db = Path(str(manifest["source_db"]))
    stat = source_db.stat()
    source_db.touch()
    with pytest.raises(repair.RawAliasRepairError, match="source 檔案身分已變更"):
        repair.validate_raw_alias_replacement(database_path, records[:1])
    source_db.touch()
    os.utime(source_db, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_db_manager_guard_preflights_stale_and_incomplete_replace_before_delete(tmp_path: Path) -> None:
    from data_module.db_manager import DBManager

    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    _run_to_audit(root, technical_receipt, new_receipt)
    manifest_hash = repair._file_hash(new_receipt / "stage" / "manifest.json")
    repair.apply(new_receipt, manifest_hash)
    manager = object.__new__(DBManager)
    manager.db_path = database_path
    manager.config = SimpleNamespace(db_file=database_path)
    manager.logger = logging.getLogger("test_raw_alias_writer_guard")

    with repair._readonly(database_path) as connection:
        original = pd.read_sql_query(
            "SELECT * FROM technical_indicators ORDER BY 證券代號,日期", connection
        )
        before = repair._table_fingerprint(connection, "technical_indicators")

    stale = original.copy()
    stale.loc[0, "最後揭示買價"] = 999
    assert manager.write_dataframe("technical_indicators", stale, if_exists="replace") is False
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before

    incomplete = original.iloc[:-1].copy()
    assert manager.write_dataframe("technical_indicators", incomplete, if_exists="replace") is False
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before

    partial = original.drop(columns=list(repair.ALIASES))
    assert manager.write_dataframe("technical_indicators", partial, if_exists="replace") is False
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before

    assert manager.write_dataframe("technical_indicators", original, if_exists="replace") is True
    with repair._readonly(database_path) as connection:
        after = repair._table_fingerprint(connection, "technical_indicators")
        assert after["schema_sha256"] == before["schema_sha256"]
        assert after["keys_sha256"] == before["keys_sha256"]

    partial_existing = pd.DataFrame([{
        "日期": "20260520",
        "證券代號": "0050",
        "RSI": 55.0,
    }])
    assert manager.write_dataframe(
        "technical_indicators", partial_existing, if_exists="append"
    ) is False
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == after

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'INSERT INTO daily_prices '
            '("證券代號","日期","最後揭示買價","最後揭示買量",'
            '"最後揭示賣價","最後揭示賣量","本益比","漲跌價差","收盤價") '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            ("0050", "20260522", 103.0, 10, 104.0, 12, 13.0, 1.0, 50.0),
        )
    # 增量 feature-only caller 可省略六欄；DBManager 會從同 key daily_prices 補齊。
    future = pd.DataFrame([{
        "日期": pd.Timestamp("2026-05-22"),
        "證券代號": 50,
        "MA5": 43.0,
    }])
    assert manager.write_dataframe("technical_indicators", future, if_exists="append") is True
    appended = manager.execute_query(
        'SELECT "日期", "證券代號","最後揭示買價","最後揭示買量",'
        '"最後揭示賣價","最後揭示賣量",本益比,漲跌價差 '
        'FROM technical_indicators WHERE "日期"="20260522"'
    )
    assert appended.to_dict(orient="records") == [{
        "日期": "20260522",
        "證券代號": "0050",
        "最後揭示買價": 103.0,
        "最後揭示買量": 10,
        "最後揭示賣價": 104.0,
        "最後揭示賣量": 12,
        "本益比": 13.0,
        "漲跌價差": 1.0,
    }]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'INSERT INTO daily_prices '
            '("證券代號","日期","最後揭示買價","最後揭示買量",'
            '"最後揭示賣價","最後揭示賣量","本益比","漲跌價差","收盤價") '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            ("0050", "20260523", None, None, 105.0, 11, 11.0, 1.0, 51.0),
        )
    formatted_aliases = pd.DataFrame([{
        "日期": "20260523",
        "證券代號": "0050",
        "最後揭示買價": "--",
        "最後揭示買量": None,
        "最後揭示賣價": "105.00",
        "最後揭示賣量": "11",
        "本益比": "11.00",
        "漲跌價差": "1.00",
        "MA5": 45.0,
    }])
    assert manager.write_dataframe(
        "technical_indicators", formatted_aliases, if_exists="append"
    ) is True
    formatted = manager.execute_query(
        'SELECT "最後揭示買價","最後揭示買量","最後揭示賣價",'
        '"最後揭示賣量",本益比,漲跌價差 FROM technical_indicators '
        'WHERE "日期"="20260523"'
    )
    assert formatted.to_dict(orient="records") == [{
        "最後揭示買價": None,
        "最後揭示買量": None,
        "最後揭示賣價": 105.0,
        "最後揭示賣量": 11,
        "本益比": 11.0,
        "漲跌價差": 1.0,
    }]


def test_unmarked_db_manager_technical_append_keeps_existing_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from data_module.db_manager import DBManager

    database_path = tmp_path / "clean-root" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    manager = object.__new__(DBManager)
    manager.db_path = database_path
    manager.config = SimpleNamespace(db_file=database_path)
    manager.logger = logging.getLogger("test_unmarked_technical_append")
    manager.init_database()
    monkeypatch.setattr(
        manager,
        "_prepare_technical_append_frame",
        lambda _frame: pytest.fail("unmarked root must not query technical/daily alias keys"),
    )

    frame = pd.DataFrame({
        "日期": ["20260529"],
        "證券代號": ["2330"],
        "RSI": [55.0],
    })
    assert manager.write_dataframe("technical_indicators", frame, if_exists="append") is True

    result = manager.execute_query(
        'SELECT "日期","證券代號",RSI FROM technical_indicators'
    )
    assert result.to_dict(orient="records") == [
        {"日期": "20260529", "證券代號": "2330", "RSI": 55.0}
    ]


def _apply_raw_alias_marker(root: Path, technical_receipt: Path, raw_alias_receipt: Path) -> Path:
    _run_to_audit(root, technical_receipt, raw_alias_receipt)
    manifest_path = raw_alias_receipt / "stage" / "manifest.json"
    repair.apply(raw_alias_receipt, repair._file_hash(manifest_path))
    return root / "sqlite" / "twstock.db"


def _update_service_and_db(database_path: Path):
    from app_module.update_service import UpdateService
    from data_module.db_manager import DBManager

    manager = object.__new__(DBManager)
    manager.db_path = database_path
    manager.config = SimpleNamespace(db_file=database_path)
    manager.logger = logging.getLogger("test_update_service_raw_alias")
    return object.__new__(UpdateService), manager


def test_update_service_upsert_hydrates_omitted_aliases_and_rejects_stale_values(tmp_path: Path) -> None:
    root, technical_receipt, raw_alias_receipt, _ = _fixture(tmp_path)
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    service, manager = _update_service_and_db(database_path)

    with repair._readonly(database_path) as connection:
        before = repair._table_fingerprint(connection, "technical_indicators")
        canonical = connection.execute(
            'SELECT "最後揭示買價","最後揭示買量","最後揭示賣價",'
            '"最後揭示賣量",本益比,漲跌價差 FROM daily_prices '
            'WHERE "日期"=? AND "證券代號"=?',
            ("20260521", "0050"),
        ).fetchone()
    assert canonical is not None

    # 模擬缺少的技術 key；日價仍在，feature-only upsert 必須從日價補六欄。
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'DELETE FROM technical_indicators WHERE "日期"=? AND "證券代號"=?',
            ("20260521", "0050"),
        )
    partial = pd.DataFrame([{
        "日期": "20260521",
        "證券代號": "0050",
        "MA5": 61.0,
    }])
    assert service._upsert_sqlite_rows(manager, "technical_indicators", partial)
    with repair._readonly(database_path) as connection:
        hydrated = connection.execute(
            'SELECT "最後揭示買價","最後揭示買量","最後揭示賣價",'
            '"最後揭示賣量",本益比,漲跌價差,MA5 FROM technical_indicators '
            'WHERE "日期"=? AND "證券代號"=?',
            ("20260521", "0050"),
        ).fetchone()
    assert hydrated == (*canonical, 61.0)

    with repair._readonly(database_path) as connection:
        before_stale = repair._table_fingerprint(connection, "technical_indicators")
    stale = pd.DataFrame([{
        "日期": "20260520",
        "證券代號": "0050",
        "最後揭示買價": 999.0,
        "MA5": 62.0,
    }])
    assert service._upsert_sqlite_rows(manager, "technical_indicators", stale) is False
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before_stale
        assert repair._table_fingerprint(connection, "technical_indicators") != before


def test_update_service_date_replace_requires_complete_protected_date_and_accepts_complete_date(tmp_path: Path) -> None:
    root, technical_receipt, raw_alias_receipt, _ = _fixture(tmp_path)
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    service, manager = _update_service_and_db(database_path)
    alias_projection = ",".join(f'"{name}"' for name in repair.ALIASES)

    with repair._readonly(database_path) as connection:
        before = repair._table_fingerprint(connection, "technical_indicators")
        one_row = connection.execute(
            f'SELECT "日期","證券代號",{alias_projection},50.0 AS MA5 FROM daily_prices '
            'WHERE "日期"=? AND "證券代號"=?',
            ("20260520", "0050"),
        ).fetchone()
        full_date_rows = connection.execute(
            f'SELECT "日期","證券代號",{alias_projection},50.0 AS MA5 FROM daily_prices '
            'WHERE "日期"=? ORDER BY "證券代號"',
            ("20260520",),
        ).fetchall()
        columns = ["日期", "證券代號", *repair.ALIASES, "MA5"]

    incomplete = pd.DataFrame([one_row], columns=columns)
    with pytest.raises(repair.RawAliasRepairError, match="日期替換缺少"):
        service._replace_sqlite_dates(manager, "technical_indicators", incomplete)
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before

    complete = pd.DataFrame(full_date_rows, columns=columns)
    assert service._replace_sqlite_dates(manager, "technical_indicators", complete)
    with repair._readonly(database_path) as connection:
        rows = connection.execute(
            'SELECT "證券代號",MA5 FROM technical_indicators WHERE "日期"=? ORDER BY "證券代號"',
            ("20260520",),
        ).fetchall()
        assert rows == [("0050", 50.0), ("2330", 50.0)]
        assert connection.execute("SELECT COUNT(*) FROM technical_indicators").fetchone()[0] == before["rows"]


def test_technical_publication_writer_guards_direct_sql_before_upsert_or_delete(tmp_path: Path) -> None:
    from app_module.update_service import _write_technical_indicator_publications

    root, technical_receipt, raw_alias_receipt, _ = _fixture(tmp_path)
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    with repair._readonly(database_path) as connection:
        before = repair._table_fingerprint(connection, "technical_indicators")
    stale = pd.DataFrame([{
        "日期": "20260520",
        "證券代號": "0050",
        "最後揭示買價": 999.0,
        "最後揭示買量": 15,
        "最後揭示賣價": 101.0,
        "最後揭示賣量": 18,
        "本益比": None,
        "漲跌價差": 2.5,
        "MA5": 90.0,
    }])
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(repair.RawAliasRepairError, match="舊來源會覆寫"):
            _write_technical_indicator_publications(
                connection,
                stale,
                replace_market=True,
                database_path=database_path,
            )
    with repair._readonly(database_path) as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == before

    partial = pd.DataFrame([{
        "日期": "20260520",
        "證券代號": "0050",
        "MA5": 91.0,
    }])
    with sqlite3.connect(database_path) as connection:
        assert _write_technical_indicator_publications(
            connection,
            partial,
            database_path=database_path,
        ) == 1
    with repair._readonly(database_path) as connection:
        row = connection.execute(
            'SELECT "最後揭示買價","最後揭示買量","最後揭示賣價",'
            '"最後揭示賣量",本益比,漲跌價差,MA5 FROM technical_indicators '
            'WHERE "日期"=? AND "證券代號"=?',
            ("20260520", "0050"),
        ).fetchone()
        assert row == (100.0, 15, 101.0, 18, None, 2.5, 91.0)

    published = pd.DataFrame([{
        "日期": "20260521",
        "證券代號": "0050",
        "最後揭示買價": "--",
        "最後揭示買量": None,
        "最後揭示賣價": "102.00",
        "最後揭示賣量": 20,
        "本益比": 13.1,
        "漲跌價差": 1.0,
        "MA5": 92.0,
    }])
    with sqlite3.connect(database_path) as connection:
        assert _write_technical_indicator_publications(
            connection,
            published,
            database_path=database_path,
        ) == 1
    with repair._readonly(database_path) as connection:
        quote = connection.execute(
            'SELECT "最後揭示買價","最後揭示賣價",MA5 '
            'FROM technical_indicators WHERE "日期"=? AND "證券代號"=?',
            ("20260521", "0050"),
        ).fetchone()
    assert quote == (None, 102.0, 92.0)


def test_update_service_calculation_rejects_stale_source_before_any_csv_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_module.update_service import UpdateService
    from data_module.config import TWStockConfig

    root, technical_receipt, raw_alias_receipt, _ = _fixture(tmp_path)
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    config = TWStockConfig(data_root=root, output_root=tmp_path / "artifacts", profile="raw_alias_guard")
    config.use_sqlite = False
    config.min_data_days = 1
    indicator_path = config.technical_dir / "0050_indicators.csv"
    aggregate_path = config.all_stocks_data_file
    indicator_before = indicator_path.read_bytes() if indicator_path.exists() else None
    aggregate_before = aggregate_path.read_bytes() if aggregate_path.exists() else None
    rows = [
        {
            "日期": "20260520",
            "證券代號": "0050",
            "開盤價": 49.0,
            "最高價": 51.0,
            "最低價": 48.0,
            "收盤價": 50.0,
            "成交股數": 1000,
            **dict(zip(repair.ALIASES, (999.0, 15, 101.0, 18, None, 2.5), strict=True)),
        },
        {
            "日期": "20260521",
            "證券代號": "0050",
            "開盤價": 50.0,
            "最高價": 52.0,
            "最低價": 49.0,
            "收盤價": 51.0,
            "成交股數": 1200,
            **dict(zip(repair.ALIASES, (None, None, 102.0, 20, 13.1, 1.0), strict=True)),
        },
    ]
    pd.DataFrame(rows).to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")

    class FailIfPublishedCalculator:
        def __init__(self, logger=None):
            self.logger = logger

        def calculate_all_indicators(self, *args, **kwargs):
            pytest.fail("stale raw alias source must stop before calculation/publication")

        def calculate_and_store_indicators(self, *args, **kwargs):
            pytest.fail("stale raw alias source must stop before CSV publication")

    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        FailIfPublishedCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        target_stock="0050",
        force_all=True,
        technical_process_pool=False,
    )
    assert result["success"] is False
    assert (indicator_path.read_bytes() if indicator_path.exists() else None) == indicator_before
    assert (aggregate_path.read_bytes() if aggregate_path.exists() else None) == aggregate_before


@pytest.mark.parametrize(
    ("bid_value", "expected_success", "expected_error"),
    [
        (None, True, None),
        ("2,150.01", False, "舊來源會覆寫"),
        ("inf", False, "不是有效數值"),
    ],
)
def test_update_service_sqlite_parses_alias_before_approved_guard_without_csv_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bid_value: str,
    expected_success: bool,
    expected_error: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app_module.update_service import UpdateService
    from data_module.config import TWStockConfig
    from data_module.db_manager import DBManager

    root, technical_receipt, raw_alias_receipt, _ = _fixture(
        tmp_path,
        alias_override_for_2330=("2,150.00", 30, "2,270.00", 32, 19.2, 5.0),
    )
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    with sqlite3.connect(database_path) as connection:
        stored_aliases = connection.execute(
            'SELECT "最後揭示買價","最後揭示賣價" FROM daily_prices '
            'WHERE "日期"=? AND "證券代號"=?',
            ("20260520", "2330"),
        ).fetchone()
    assert stored_aliases == ("2,150.00", "2,270.00")
    config = TWStockConfig(
        data_root=root,
        output_root=tmp_path / "artifacts",
        profile="raw_alias_guard",
    )
    config.db_file = database_path
    config.use_sqlite = True
    config.min_data_days = 1
    config.stock_data_file.parent.mkdir(parents=True, exist_ok=True)
    fallback_frame = pd.DataFrame([{
        "日期": "20260520",
        "證券代號": "2330",
        "開盤價": "1490",
        "最高價": "1510",
        "最低價": "1480",
        "收盤價": "1500",
        "成交股數": "1000",
        "最後揭示買價": "2,150.00",
        "最後揭示買量": "30",
        "最後揭示賣價": "2,270.00",
        "最後揭示賣量": "32",
        "本益比": "19.2",
        "漲跌價差": "5.0",
    }])
    fallback_frame.to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")

    execute_query = DBManager.execute_query

    def _query_with_grouped_sqlite_aliases(self, sql: str, params: tuple = ()):
        frame = execute_query(self, sql, params)
        if sql.strip().startswith("SELECT * FROM daily_prices"):
            frame = frame.copy()
            if bid_value is not None:
                frame["最後揭示買價"] = frame["最後揭示買價"].astype(object)
                target = (frame["日期"].astype(str) == "20260520") & (
                    frame["證券代號"].astype(str).str.strip() == "2330"
                )
                frame.loc[target, "最後揭示買價"] = bid_value
        return frame

    monkeypatch.setattr(DBManager, "execute_query", _query_with_grouped_sqlite_aliases)

    read_csv = pd.read_csv
    fallback_reads: list[Path] = []

    def _track_csv_fallback(path, *args, **kwargs):
        if Path(path).resolve() == config.stock_data_file.resolve():
            fallback_reads.append(Path(path))
        return read_csv(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", _track_csv_fallback)

    observed: list[tuple[object, ...]] = []

    class _CaptureCalculator:
        def __init__(self, _logger=None) -> None:
            pass

        def calculate_all_indicators(self, frame, _stock_id):
            observed.append(tuple(frame.iloc[0][name] for name in repair.ALIASES))
            return frame.assign(RSI=55.0)

        def calculate_and_store_indicators(self, _frame, _stock_id, **kwargs):
            return kwargs["precomputed_result"]

    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        _CaptureCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        target_stock="2330",
        force_all=True,
        technical_process_pool=False,
    )

    assert result["success"] is expected_success
    assert fallback_reads == []
    if expected_success:
        assert observed == [(2150.0, 30, 2270.0, 32, 19.2, 5.0)]
    else:
        assert observed == []
        assert expected_error is not None
        if expected_error == "舊來源會覆寫":
            assert result["fail_count"] == 1
            assert result["failed_stocks"] == ["2330"]
            assert expected_error in caplog.text
        else:
            assert expected_error in result["message"]



def test_update_service_full_rebuild_keeps_existing_five_and_six_character_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app_module.update_service import UpdateService
    from data_module.config import TWStockConfig

    root, technical_receipt, raw_alias_receipt, _ = _fixture(
        tmp_path,
        include_extended_symbol=True,
        include_second_extended_symbol=True,
    )
    database_path = _apply_raw_alias_marker(root, technical_receipt, raw_alias_receipt)
    config = TWStockConfig(
        data_root=root,
        output_root=tmp_path / "artifacts",
        profile="raw_alias_full_market",
    )
    config.use_sqlite = True
    config.min_data_days = 1

    source_rows = []
    for day, symbol, bid, bid_volume, ask, ask_volume, pe, change in _canonical_rows(
        include_extended_symbol=True,
        include_second_extended_symbol=True,
    ):
        source_rows.append({
            "日期": f"{day[:4]}-{day[4:6]}-{day[6:]}",
            "證券代號": symbol,
            "開盤價": 49.0,
            "最高價": 51.0,
            "最低價": 48.0,
            "收盤價": 50.0,
            "成交股數": 1000,
            "最後揭示買價": bid,
            "最後揭示買量": bid_volume,
            "最後揭示賣價": ask,
            "最後揭示賣量": ask_volume,
            "本益比": pe,
            "漲跌價差": change,
        })
    # Feed an unknown symbol through the raw input; marker mode must not expand the
    # publication universe beyond symbols already present in daily_prices.
    source_rows.append({
        "日期": "2026-05-20",
        "證券代號": "99999",
        "開盤價": 49.0,
        "最高價": 51.0,
        "最低價": 48.0,
        "收盤價": 50.0,
        "成交股數": 1000,
        "最後揭示買價": 49.0,
        "最後揭示買量": 10,
        "最後揭示賣價": 51.0,
        "最後揭示賣量": 12,
        "本益比": 13.0,
        "漲跌價差": 1.0,
    })
    pd.DataFrame(source_rows).to_csv(
        config.stock_data_file, index=False, encoding="utf-8-sig"
    )

    class CopyCalculator:
        def __init__(self, logger=None):
            self.logger = logger

        def calculate_all_indicators(self, frame, stock_id):
            result = frame.copy()
            result["MA5"] = result["收盤價"]
            return result

        def calculate_and_store_indicators(
            self,
            frame,
            stock_id,
            *,
            output_dir,
            precomputed_result=None,
            **kwargs,
        ):
            result = precomputed_result.copy()
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            result.to_csv(
                Path(output_dir) / f"{stock_id}_indicators.csv",
                index=False,
                encoding="utf-8-sig",
            )
            return result

    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        CopyCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        force_all=True,
        technical_process_pool=False,
    )

    assert result["success"] is True
    assert result["success_count"] == 4
    expected_symbols = {"0050", "2330", "1101B", "2887Z1"}
    aggregate = pd.read_csv(config.all_stocks_data_file, dtype={"證券代號": str})
    assert set(aggregate["證券代號"]) == expected_symbols
    assert len(aggregate) == 8
    for symbol in ("1101B", "2887Z1"):
        per_stock = pd.read_csv(
            config.technical_dir / f"{symbol}_indicators.csv",
            dtype={"證券代號": str},
        )
        assert set(per_stock["證券代號"]) == {symbol}
        assert len(per_stock) == 2

    with repair._readonly(database_path) as connection:
        technical_keys = connection.execute(
            'SELECT "證券代號","日期" FROM technical_indicators ORDER BY "證券代號","日期"'
        ).fetchall()
    assert len(technical_keys) == 8
    assert {symbol for symbol, _ in technical_keys} == expected_symbols


def test_technical_migration_accepts_applied_session_marker_and_existing_extended_symbol(tmp_path: Path) -> None:
    from data_module import historical_session_revision
    from data_module.db_manager import DBManager
    from data_module.historical_session_revision import validate_session_replacement
    from scripts import migrate_csv_to_sqlite as migration

    root, technical_receipt, new_receipt, _ = _fixture(
        tmp_path, include_extended_symbol=True
    )
    database_path = root / "sqlite" / "twstock.db"
    _manifest, manifest_hash = _run_to_audit(root, technical_receipt, new_receipt)
    repair.apply(new_receipt, manifest_hash)

    # 建立可驗證的 applied session marker；價量資料完整，日期包含六碼代號 1101B。
    session_rows = [
        {
            "日期": "20260520",
            "證券代號": symbol,
            "成交股數": 1000,
            "成交筆數": 10,
            "成交金額": 50000,
            "開盤價": 49.0,
            "最高價": 51.0,
            "最低價": 48.0,
            "收盤價": 50.0,
            "漲跌價差": 1.0,
        }
        for symbol in ("0050", "2330", "1101B")
    ]
    session_dir = root / historical_session_revision.RECEIPT_DIR / "fixture_run01"
    session_dir.mkdir(parents=True)
    plan = {
        "schema_version": "historical-session-repair.v1",
        "database_path": str(database_path.resolve()),
        "source_start_date": "2026-05-20",
        "dates": ["20260520"],
        "rows": session_rows,
    }
    plan_bytes = repair._json_bytes(plan)
    (session_dir / "plan.json").write_bytes(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    session_receipt_bytes = repair._json_bytes({
        "state": "applied",
        "plan_sha256": plan_hash,
        "dates": plan["dates"],
    })
    (session_dir / "receipt.json").write_bytes(session_receipt_bytes)
    (session_dir / "revision.json").write_bytes(repair._json_bytes({
        "schema_version": "historical-session-revision.v1",
        "database_path": str(database_path.resolve()),
        "plan_sha256": plan_hash,
        "state": "applied",
        "historical_pit": False,
        "receipt_sha256": hashlib.sha256(session_receipt_bytes).hexdigest(),
    }))
    validate_session_replacement(database_path, session_rows, replace_all=True)

    db = object.__new__(DBManager)
    db.db_path = database_path
    db.logger = logging.getLogger("test_technical_migration")
    config = SimpleNamespace(technical_dir=root / "technical_analysis")
    migration.migrate_technical_indicators(config, db, db.logger)

    with sqlite3.connect(database_path) as connection:
        technical_keys = connection.execute(
            'SELECT "證券代號","日期" FROM technical_indicators ORDER BY "證券代號","日期"'
        ).fetchall()
        mismatches = connection.execute(
            'SELECT COUNT(*) FROM technical_indicators t '
            'JOIN daily_prices d USING("證券代號","日期") '
            'WHERE t."最後揭示買價" IS NOT d."最後揭示買價" '
            'OR t."最後揭示買量" IS NOT d."最後揭示買量" '
            'OR t."最後揭示賣價" IS NOT d."最後揭示賣價" '
            'OR t."最後揭示賣量" IS NOT d."最後揭示賣量" '
            'OR t."本益比" IS NOT d."本益比" '
            'OR t."漲跌價差" IS NOT d."漲跌價差"'
        ).fetchone()[0]
    assert len(technical_keys) == 6
    assert ("1101B", "20260520") in technical_keys
    assert mismatches == 0


def test_technical_migration_second_batch_failure_rolls_back_original_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from data_module.db_manager import DBManager
    from scripts import migrate_csv_to_sqlite as migration

    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    _manifest, manifest_hash = _run_to_audit(root, technical_receipt, new_receipt)
    repair.apply(new_receipt, manifest_hash)
    monkeypatch.setattr(migration, "TECHNICAL_MIGRATION_CHUNK_SIZE", 2)
    db = object.__new__(DBManager)
    db.db_path = database_path
    db.logger = logging.getLogger("test_technical_migration_rollback")
    # 技術指標 migration 的合法 schema preflight 先完成；故障注入只驗資料交易回滾。
    db.ensure_columns("technical_indicators", ["註記"])
    with sqlite3.connect(database_path) as connection:
        before_hash = repair._table_hash(connection, "technical_indicators")
        connection.execute(
            "CREATE TRIGGER fail_second_technical_migration_batch "
            'BEFORE INSERT ON technical_indicators WHEN NEW."證券代號"="2330" '
            "BEGIN SELECT RAISE(ABORT,'migration batch fault'); END"
        )
    config = SimpleNamespace(technical_dir=root / "technical_analysis")

    with pytest.raises(sqlite3.IntegrityError, match="migration batch fault"):
        migration.migrate_technical_indicators(config, db, db.logger)

    with sqlite3.connect(database_path) as connection:
        assert repair._table_hash(connection, "technical_indicators") == before_hash
        assert connection.execute(
            "SELECT COUNT(*) FROM technical_indicators"
        ).fetchone()[0] == len(_canonical_rows())


def test_legacy_calculator_guard_preserves_no_marker_and_stops_applied_marker_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys

    root, technical_receipt, new_receipt, _ = _fixture(tmp_path)
    database_path = root / "sqlite" / "twstock.db"
    saved_stdout, saved_stderr = sys.stdout, sys.stderr
    try:
        legacy = importlib.import_module("scripts.calculate_technical_indicators")
    finally:
        wrapped_stdout, wrapped_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = saved_stdout, saved_stderr
        for wrapped in (wrapped_stdout, wrapped_stderr):
            if wrapped not in (saved_stdout, saved_stderr):
                try:
                    wrapped.detach()
                except Exception:
                    pass
    config = SimpleNamespace(
        db_file=database_path,
        data_dir=root,
        stock_data_file=tmp_path / "missing-stock-source.csv",
    )
    read_attempts: list[str] = []

    def probe_read_csv(*_args: object, **_kwargs: object) -> pd.DataFrame:
        read_attempts.append("called")
        raise RuntimeError("測試用：legacy reader reached")

    monkeypatch.setattr(legacy.pd, "read_csv", probe_read_csv)
    # 無 applied marker 時，舊入口仍通過 writer preflight 並維持舊讀取流程。
    no_marker = legacy.process_stock_data_batch(
        config, object(), logging.getLogger("test_legacy_calculator_no_marker")
    )
    assert no_marker["fail_count"] == 1
    assert read_attempts == ["called"]

    _manifest, manifest_hash = _run_to_audit(root, technical_receipt, new_receipt)
    repair.apply(new_receipt, manifest_hash)
    targets = [
        root / "technical_analysis" / "0050_indicators.csv",
        root / "technical_analysis" / "2330_indicators.csv",
        root / "meta_data" / "all_stocks_data.csv",
    ]
    before_files = {str(path): repair._file_hash(path) for path in targets}
    before_database = repair._file_hash(database_path)

    read_attempts.clear()
    blocked = legacy.process_stock_data_batch(
        config, object(), logging.getLogger("test_legacy_calculator_applied_marker")
    )
    assert blocked["fail_count"] == 1
    assert read_attempts == []
    assert repair._file_hash(database_path) == before_database
    assert {str(path): repair._file_hash(path) for path in targets} == before_files


def test_full_table_hash_matches_technical_publisher_after_5001_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "hash.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute('CREATE TABLE daily_prices("證券代號" TEXT,"日期" TEXT,"value" INTEGER)')
        connection.executemany(
            "INSERT INTO daily_prices VALUES(?,?,?)",
            [(f"{number % 99 + 1:04d}", f"{20140000 + number:08d}", number) for number in range(5001)],
        )
        expected = _table_hash_like_publisher(connection, "daily_prices")
        actual = repair._table_hash(connection, "daily_prices")
    assert actual == expected
