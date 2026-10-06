from __future__ import annotations

import shutil
from pathlib import Path
import sqlite3

import pytest

from data_module import formal_technical_raw_alias_repair as repair
from test_formal_technical_raw_alias_repair import _fixture, _run_to_audit


def test_audit_and_apply_reject_csv_target_outside_prepared_inventory(
    tmp_path: Path,
) -> None:
    root, technical_receipt, receipt_dir, original_hashes = _fixture(tmp_path)
    repair.prepare(root, technical_receipt, receipt_dir)
    repair.stage(receipt_dir)

    manifest_path = receipt_dir / "stage" / "manifest.json"
    manifest = repair._read_sealed(manifest_path)
    aggregate_entry = next(
        item for item in manifest["csv_targets"]
        if Path(item["target_path"]).name == "all_stocks_data.csv"
    )
    aggregate_source = Path(aggregate_entry["target_path"])
    redirected = tmp_path / "outside-formal-root" / "all_stocks_data.csv"
    redirected.parent.mkdir()
    shutil.copyfile(aggregate_source, redirected)
    redirected_before = repair._file_hash(redirected)
    aggregate_entry["target_path"] = str(redirected.resolve())
    repair._write_sealed(manifest_path, manifest)
    manifest_hash = repair._file_hash(manifest_path)

    with pytest.raises(repair.RawAliasRepairError, match="inventory|目標|target|越界"):
        repair.audit(receipt_dir, manifest_hash)
    assert not (receipt_dir / "audit.json").exists()

    # Even a matching, resealed audit record cannot bypass _load_stage's inventory gate.
    repair._write_sealed(
        receipt_dir / "audit.json",
        {"state": "passed", "manifest_sha256": manifest_hash},
    )
    with pytest.raises(repair.RawAliasRepairError, match="inventory|目標|target|越界"):
        repair.apply(receipt_dir, manifest_hash)

    assert repair._file_hash(redirected) == redirected_before
    assert repair._file_hash(aggregate_source) == original_hashes[str(aggregate_source)]
    assert not (receipt_dir / "journal.json").exists()


def test_resume_rejects_journal_changed_while_waiting_for_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, technical_receipt, receipt_dir, original_hashes = _fixture(tmp_path)
    _manifest, manifest_hash = _run_to_audit(root, technical_receipt, receipt_dir)

    original_apply_database = repair._apply_database

    def fail_before_database_commit(*args, **kwargs):
        raise OSError("fixture interruption before database commit")

    monkeypatch.setattr(repair, "_apply_database", fail_before_database_commit)
    with pytest.raises(OSError, match="before database commit"):
        repair.apply(receipt_dir, manifest_hash)
    monkeypatch.setattr(repair, "_apply_database", original_apply_database)
    assert repair._read_sealed(receipt_dir / "journal.json")["state"] == "pending"

    original_acquire = repair._acquire_lock
    interleaved_rollbacks: list[dict[str, object]] = []

    def rollback_before_resume_acquires_lock(data_root: Path):
        # Model a second recovery command that read the same pending journal and
        # completed rollback while this resume was queued for the heavy-chain lock.
        monkeypatch.setattr(repair, "_acquire_lock", original_acquire)
        try:
            interleaved_rollbacks.append(
                repair.recover(
                    receipt_dir,
                    rollback=True,
                    expected_manifest_hash=manifest_hash,
                )
            )
        finally:
            monkeypatch.setattr(repair, "_acquire_lock", rollback_before_resume_acquires_lock)
        return original_acquire(data_root)

    monkeypatch.setattr(repair, "_acquire_lock", rollback_before_resume_acquires_lock)
    with pytest.raises(repair.RawAliasRepairError, match="journal.*變更"):
        repair.recover(
            receipt_dir,
            rollback=False,
            expected_manifest_hash=manifest_hash,
        )
    monkeypatch.setattr(repair, "_acquire_lock", original_acquire)

    assert interleaved_rollbacks == [{"state": "rolled_back", "database_rows": 0, "csv_targets": 3}]
    assert repair._read_sealed(receipt_dir / "journal.json")["state"] == "rolled_back"
    with repair._readonly(root / "sqlite" / "twstock.db") as connection:
        assert repair._table_fingerprint(connection, "technical_indicators") == repair._read_sealed(
            receipt_dir / "stage" / "manifest.json"
        )["database_before"]
    for path_text, expected_hash in original_hashes.items():
        if path_text.endswith(".csv"):
            assert repair._file_hash(Path(path_text)) == expected_hash
