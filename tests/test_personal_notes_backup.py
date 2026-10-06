from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Callable

import pytest

import app_module.personal_notes_backup as backup_module
from app_module.journal_service import JournalService
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_journal_paths import PersonalJournalPaths
from app_module.personal_notes_backup import (
    PersonalNotesBackupAdapter,
    PersonalNotesBackupError,
)


IDENTITY = "research-account:synthetic-01"


def _journal_paths(base: Path) -> PersonalJournalPaths:
    market_root = base / "FA_Data"
    return PersonalJournalPaths(
        PersonalDataPaths(
            market_root=market_root,
            legacy_output_root=base / "output",
            personal_root=market_root / "personal",
        )
    )


def _adapter(
    paths: PersonalJournalPaths, *, identity: str = IDENTITY, max_bytes: int = 4096
) -> PersonalNotesBackupAdapter:
    return PersonalNotesBackupAdapter(paths, store_identity=identity, max_bytes=max_bytes)


def _seed_notes(paths: PersonalJournalPaths, *, body: str = "synthetic research note") -> bytes:
    config = SimpleNamespace(
        output_root=paths.personal_paths.legacy_output_root,
        personal_journal_root=None,
        personal_journal_mode=None,
    )
    service = JournalService(config, journal_paths=paths)  # type: ignore[arg-type]
    service.add_journal_entry(body=body, journal_id="synthetic-note-001", title="fixture")
    return paths.journal_file.read_bytes()


def _backup_paths(paths: PersonalJournalPaths) -> tuple[Path, Path]:
    return (
        paths.backup_root / "notes-snapshot.jsonl",
        paths.backup_root / "notes-receipt.json",
    )


def _create_backup(paths: PersonalJournalPaths) -> tuple[PersonalNotesBackupAdapter, Path, bytes]:
    source_bytes = _seed_notes(paths)
    adapter = _adapter(paths)
    snapshot, receipt = _backup_paths(paths)
    result = adapter.backup(snapshot, receipt, confirmed=True)
    assert result.created
    return adapter, receipt, source_bytes


def _journal_read_in_fresh_process(paths: PersonalJournalPaths) -> list[dict[str, str]]:
    script = r'''
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from app_module.journal_service import JournalService
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_journal_paths import PersonalJournalPaths
market_root = Path(sys.argv[1])
output_root = Path(sys.argv[2])
paths = PersonalJournalPaths(PersonalDataPaths(
    market_root=market_root,
    legacy_output_root=output_root,
    personal_root=market_root / "personal",
))
config = SimpleNamespace(
    output_root=output_root,
    personal_journal_root=None,
    personal_journal_mode=None,
)
service = JournalService(config, journal_paths=paths)
print(json.dumps([
    {"journal_id": item.journal_id, "body": item.body, "title": item.title}
    for item in service.list_journal_entries()
], ensure_ascii=False))
'''
    repo_root = Path(__file__).resolve().parents[1]
    child_env = os.environ.copy()
    child_env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    completed = subprocess.run(
        [
            sys.executable,
            "-Xutf8",
            "-c",
            script,
            str(paths.personal_paths.market_root),
            str(paths.personal_paths.legacy_output_root),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env,
    )
    return json.loads(completed.stdout)


def test_dry_run_and_create_only_backup_restore_round_trip_in_fresh_process(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_before = _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)

    planned = adapter.backup(snapshot_path, receipt_path)
    assert not planned.created
    assert planned.source_path == source_paths.journal_file
    assert planned.source_size_bytes == len(source_before)
    assert planned.source_sha256 == hashlib.sha256(source_before).hexdigest()
    assert planned.snapshot_sha256 == planned.source_sha256
    assert planned.receipt_sha256 == hashlib.sha256(
        json.dumps(
            {
                "schema_version": planned.schema_version,
                "store_identity": IDENTITY,
                "source": {
                    "canonical_path": str(planned.source_path),
                    "size_bytes": planned.source_size_bytes,
                    "sha256": planned.source_sha256,
                },
                "snapshot": {
                    "canonical_path": str(planned.snapshot_path),
                    "size_bytes": planned.snapshot_size_bytes,
                    "sha256": planned.snapshot_sha256,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()
    assert not source_paths.backup_root.exists()
    assert not snapshot_path.exists()
    assert not receipt_path.exists()

    receipt = adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert receipt.created
    assert receipt.receipt_sha256 == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    manifest = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "personal-notes-backup.v1"
    assert manifest["store_identity"] == IDENTITY
    assert manifest["source"]["canonical_path"] == str(source_paths.journal_file)
    assert manifest["source"]["size_bytes"] == len(source_before)
    assert manifest["source"]["sha256"] == hashlib.sha256(source_before).hexdigest()
    assert manifest["snapshot"]["canonical_path"] == str(snapshot_path)
    assert manifest["snapshot"]["size_bytes"] == len(source_before)
    assert manifest["snapshot"]["sha256"] == hashlib.sha256(source_before).hexdigest()
    assert snapshot_path.read_bytes() == source_before
    assert source_paths.journal_file.read_bytes() == source_before

    target_paths = _journal_paths(tmp_path / "restored")
    restore_plan = adapter.restore_into(
        target_paths,
        receipt_path,
        expected_receipt_sha256=receipt.receipt_sha256,
    )
    assert not restore_plan.restored
    assert restore_plan.target_path == target_paths.journal_file
    assert not target_paths.journal_file.exists()
    assert not target_paths.journal_file.parent.exists()

    restored = adapter.restore_into(
        target_paths,
        receipt_path,
        expected_receipt_sha256=receipt.receipt_sha256,
        confirmed=True,
    )
    assert restored.restored
    assert restored.store_identity == IDENTITY
    assert restored.target_path == target_paths.journal_file
    assert restored.snapshot_sha256 == hashlib.sha256(source_before).hexdigest()
    assert target_paths.journal_file.read_bytes() == source_before
    assert source_paths.journal_file.read_bytes() == source_before
    assert _journal_read_in_fresh_process(target_paths) == [
        {
            "journal_id": "synthetic-note-001",
            "body": "synthetic research note",
            "title": "fixture",
        }
    ]


def test_cancelled_operations_do_not_create_directories_or_outputs(tmp_path: Path) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)

    with pytest.raises(PersonalNotesBackupError) as backup_error:
        adapter.backup(snapshot_path, receipt_path, confirmed=True, cancel_check=lambda: True)
    assert backup_error.value.code == "cancelled"
    assert not source_paths.backup_root.exists()
    assert not snapshot_path.exists()
    assert not receipt_path.exists()

    restore_source = _journal_paths(tmp_path / "restore-source")
    restore_adapter, restore_receipt, _ = _create_backup(restore_source)
    target_paths = _journal_paths(tmp_path / "restore-target")
    with pytest.raises(PersonalNotesBackupError) as restore_error:
        restore_adapter.restore_into(
            target_paths,
            restore_receipt,
            expected_receipt_sha256=hashlib.sha256(
                restore_receipt.read_bytes()
            ).hexdigest(),
            confirmed=True,
            cancel_check=lambda: True,
        )
    assert restore_error.value.code == "cancelled"
    assert not target_paths.journal_file.parent.exists()


def test_cancellation_during_source_read_still_has_no_backup_directory(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    calls = 0

    def cancel_on_first_read_check() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(
            snapshot_path,
            receipt_path,
            confirmed=True,
            cancel_check=cancel_on_first_read_check,
        )
    assert exc_info.value.code == "cancelled"
    assert not source_paths.backup_root.exists()
    assert not snapshot_path.exists()
    assert not receipt_path.exists()


def test_byte_budget_identity_and_backup_scope_are_required(tmp_path: Path) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_bytes = _seed_notes(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)

    with pytest.raises(PersonalNotesBackupError) as budget_error:
        _adapter(source_paths, max_bytes=len(source_bytes) - 1).backup(
            snapshot_path, receipt_path, confirmed=True
        )
    assert budget_error.value.code == "notes_source_exceeds_byte_budget"
    assert not source_paths.backup_root.exists()

    with pytest.raises(PersonalNotesBackupError) as identity_error:
        _adapter(source_paths, identity="  ")
    assert identity_error.value.code == "store_identity_unknown"

    with pytest.raises(PersonalNotesBackupError) as budget_type_error:
        _adapter(source_paths, max_bytes=True)
    assert budget_type_error.value.code == "positive_byte_budget_required"

    outside_snapshot = tmp_path / "outside.jsonl"
    with pytest.raises(PersonalNotesBackupError) as outside_error:
        _adapter(source_paths).backup(outside_snapshot, receipt_path)
    assert outside_error.value.code == "backup_output_must_be_direct_child"


def test_large_identity_rejects_unrestorable_receipt_before_any_output(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    _seed_notes(source_paths)
    adapter = _adapter(source_paths, identity="account-" + "x" * 40_000)
    snapshot_path, receipt_path = _backup_paths(source_paths)

    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert exc_info.value.code == "receipt_exceeds_byte_budget"
    assert not source_paths.backup_root.exists()
    assert not snapshot_path.exists()
    assert not receipt_path.exists()


def test_missing_notes_source_is_refused_without_creating_backup_root(
    tmp_path: Path,
) -> None:
    paths = _journal_paths(tmp_path / "source")
    adapter = _adapter(paths)
    snapshot_path, receipt_path = _backup_paths(paths)

    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert exc_info.value.code == "notes_source_missing"
    assert not paths.backup_root.exists()


def test_backup_refuses_existing_outputs_without_overwriting(tmp_path: Path) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_before = _seed_notes(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(b"existing snapshot sentinel")

    with pytest.raises(PersonalNotesBackupError) as exc_info:
        _adapter(source_paths).backup(snapshot_path, receipt_path, confirmed=True)
    assert exc_info.value.code == "backup_output_exists"
    assert snapshot_path.read_bytes() == b"existing snapshot sentinel"
    assert not receipt_path.exists()
    assert source_paths.journal_file.read_bytes() == source_before


def test_restore_checks_pin_identity_snapshot_hash_and_target_existence(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    adapter, receipt_path, source_bytes = _create_backup(source_paths)
    target_paths = _journal_paths(tmp_path / "target")
    snapshot_path = _backup_paths(source_paths)[0]
    expected_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    with pytest.raises(PersonalNotesBackupError) as pin_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256="0" * 64,
        )
    assert pin_error.value.code == "receipt_pin_mismatch"
    assert not target_paths.journal_file.parent.exists()

    with pytest.raises(PersonalNotesBackupError) as identity_error:
        _adapter(source_paths, identity="different-account").restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=expected_sha,
        )
    assert identity_error.value.code == "receipt_identity_mismatch"
    assert not target_paths.journal_file.parent.exists()

    snapshot_path.write_bytes(b"x" * (len(source_bytes) + 1))
    with pytest.raises(PersonalNotesBackupError) as size_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=expected_sha,
        )
    assert size_error.value.code == "snapshot_size_mismatch"
    assert not target_paths.journal_file.parent.exists()

    snapshot_path.write_bytes(b"x" * len(source_bytes))
    with pytest.raises(PersonalNotesBackupError) as hash_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=expected_sha,
        )
    assert hash_error.value.code == "snapshot_hash_mismatch"
    assert not target_paths.journal_file.parent.exists()

    snapshot_path.write_bytes(source_bytes)
    target_paths.journal_file.parent.mkdir(parents=True)
    target_paths.journal_file.write_bytes(b"pre-existing target")
    with pytest.raises(PersonalNotesBackupError) as target_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=expected_sha,
            confirmed=True,
        )
    assert target_error.value.code == "restore_target_exists"
    assert target_paths.journal_file.read_bytes() == b"pre-existing target"


def test_restore_rejects_unsupported_schema_and_receipt_size_mismatch(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    adapter, receipt_path, _ = _create_backup(source_paths)
    target_paths = _journal_paths(tmp_path / "target")
    manifest = json.loads(receipt_path.read_text(encoding="utf-8"))

    manifest["schema_version"] = "unsupported.v99"
    receipt_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    with pytest.raises(PersonalNotesBackupError) as schema_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        )
    assert schema_error.value.code == "receipt_schema_unsupported"
    assert not target_paths.journal_file.parent.exists()

    manifest["schema_version"] = "personal-notes-backup.v1"
    manifest["snapshot"]["size_bytes"] += 1
    receipt_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    with pytest.raises(PersonalNotesBackupError) as size_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        )
    assert size_error.value.code == "receipt_source_snapshot_mismatch"
    assert not target_paths.journal_file.parent.exists()


def test_failed_second_create_preserves_snapshot_and_partial_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_bytes = _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    original_write = backup_module._exclusive_create_write

    def fail_after_partial_receipt(
        path: Path,
        payload: bytes,
        *,
        cancel_check: Callable[[], bool] | None,
    ) -> None:
        if path == receipt_path:
            original_write(path, payload[:3], cancel_check=None)
            raise PersonalNotesBackupError("fixture_receipt_write_failure")
        original_write(path, payload, cancel_check=cancel_check)

    monkeypatch.setattr(backup_module, "_exclusive_create_write", fail_after_partial_receipt)
    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert exc_info.value.code == "fixture_receipt_write_failure"
    assert snapshot_path.read_bytes() == source_bytes
    assert receipt_path.read_bytes() == b"{\"s"


def test_receipt_readback_failure_preserves_snapshot_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_bytes = _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    original_read = backup_module._read_bounded_personal_file

    def alter_receipt_readback(
        paths: PersonalDataPaths,
        path: Path,
        *,
        max_bytes: int,
        missing_code: str,
        too_large_code: str,
        cancel_check: Callable[[], bool] | None,
    ) -> bytes:
        data = original_read(
            paths,
            path,
            max_bytes=max_bytes,
            missing_code=missing_code,
            too_large_code=too_large_code,
            cancel_check=cancel_check,
        )
        return data + b"tampered readback" if path == receipt_path else data

    monkeypatch.setattr(
        backup_module, "_read_bounded_personal_file", alter_receipt_readback
    )
    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert exc_info.value.code == "receipt_verification_failed"
    assert snapshot_path.read_bytes() == source_bytes
    assert receipt_path.exists()


def test_cancel_before_receipt_create_preserves_verified_snapshot_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    source_bytes = _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    state = {"cancel": False}
    original_read = backup_module._read_bounded_personal_file

    def cancel_after_snapshot_readback(
        paths: PersonalDataPaths,
        path: Path,
        *,
        max_bytes: int,
        missing_code: str,
        too_large_code: str,
        cancel_check: Callable[[], bool] | None,
    ) -> bytes:
        data = original_read(
            paths,
            path,
            max_bytes=max_bytes,
            missing_code=missing_code,
            too_large_code=too_large_code,
            cancel_check=cancel_check,
        )
        if path == snapshot_path:
            state["cancel"] = True
        return data

    monkeypatch.setattr(
        backup_module, "_read_bounded_personal_file", cancel_after_snapshot_readback
    )
    with pytest.raises(PersonalNotesBackupError) as exc_info:
        adapter.backup(
            snapshot_path,
            receipt_path,
            confirmed=True,
            cancel_check=lambda: state["cancel"],
        )
    assert exc_info.value.code == "cancelled"
    assert snapshot_path.read_bytes() == source_bytes
    assert not receipt_path.exists()


def test_restore_rejects_corrupt_receipt_and_snapshot_path_outside_backup_root(
    tmp_path: Path,
) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    adapter, receipt_path, _ = _create_backup(source_paths)
    target_paths = _journal_paths(tmp_path / "target")
    original_receipt_bytes = receipt_path.read_bytes()

    receipt_path.write_bytes(b"{not-json")
    corrupt_pin = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    with pytest.raises(PersonalNotesBackupError) as corrupt_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=corrupt_pin,
        )
    assert corrupt_error.value.code == "receipt_invalid_json"
    assert not target_paths.journal_file.parent.exists()

    # Recreate a valid pinned manifest, then point it outside the owned backup root.
    manifest = json.loads(original_receipt_bytes.decode("utf-8"))
    manifest["snapshot"]["canonical_path"] = str(tmp_path / "outside-snapshot.jsonl")
    receipt_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    modified_pin = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    with pytest.raises(PersonalNotesBackupError) as path_error:
        adapter.restore_into(
            target_paths,
            receipt_path,
            expected_receipt_sha256=modified_pin,
        )
    assert path_error.value.code in {
        "personal_store_path_outside_root",
        "backup_output_must_be_direct_child",
    }
    assert not target_paths.journal_file.parent.exists()


def test_source_hardlink_is_rejected(tmp_path: Path) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    alias = source_paths.journal_file.with_name("journal-hardlink.jsonl")
    try:
        os.link(source_paths.journal_file, alias)
    except OSError as exc:
        pytest.skip(f"filesystem does not support local hard links: {exc}")

    with pytest.raises(PersonalNotesBackupError) as hardlink_error:
        adapter.backup(snapshot_path, receipt_path, confirmed=True)
    assert hardlink_error.value.code == "personal_store_alias_or_type"
    assert not source_paths.backup_root.exists()


def test_backup_symlink_is_rejected(tmp_path: Path) -> None:
    source_paths = _journal_paths(tmp_path / "source")
    _seed_notes(source_paths)
    adapter = _adapter(source_paths)
    snapshot_path, receipt_path = _backup_paths(source_paths)
    source_paths.backup_root.mkdir(parents=True)
    external = tmp_path / "external.jsonl"
    external.write_bytes(b"external sentinel")
    try:
        os.symlink(external, snapshot_path)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    with pytest.raises(PersonalNotesBackupError) as symlink_error:
        adapter.backup(snapshot_path, receipt_path)
    assert symlink_error.value.code == "linked_path"
    assert external.read_bytes() == b"external sentinel"
