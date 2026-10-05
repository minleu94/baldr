from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from data_module.contracts.source_revision import SourceEvidenceNamespaceV1
from data_module import excluded_daily_price_revision
from data_module import formal_market_revision
from data_module import historical_session_revision
import data_module.ml_daily_price_revision_gate as gate


def _pin(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _context_inputs(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wal_absent: bool = False,
) -> tuple[Path, Path, Path, str, str, datetime, datetime]:
    source = root / "data" / "twstock.db"
    snapshot = root / "output" / "ml_research" / "snapshot.sqlite"
    wal = root / "data" / "twstock.db-wal"
    source.parent.mkdir(parents=True)
    snapshot.parent.mkdir(parents=True)
    source_connection = sqlite3.connect(source)
    source_connection.execute("PRAGMA journal_mode=WAL")
    source_connection.execute("CREATE TABLE source_pin_fixture (value INTEGER)")
    source_connection.execute("INSERT INTO source_pin_fixture VALUES (1)")
    source_connection.commit()
    source_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    source_connection.close()
    snapshot.write_bytes(b"consistent snapshot bytes")
    if not wal_absent:
        wal.write_bytes(b"")

    namespace_roots = (
        (
            SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
            root / "data" / gate.REPAIR_RECEIPT_RELATIVE_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.MARKET_REVISION,
            root / "data" / formal_market_revision.RECEIPT_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
            root / "data" / historical_session_revision.RECEIPT_DIR,
        ),
        (
            SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION,
            root / "data" / excluded_daily_price_revision.RECEIPT_DIR,
        ),
    )
    namespace_files = []
    namespace_hashes: dict[str, str] = {}
    namespace_paths: dict[str, Path] = {}
    for namespace, namespace_root in namespace_roots:
        path = namespace_root / "evidence.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{namespace.value} evidence".encode("ascii"))
        pinned = _pin(path)
        namespace_files.append(pinned)
        namespace_hashes[namespace.value] = str(pinned["sha256"])
        namespace_paths[namespace.value] = path

    completed_at = "2026-10-03T00:23:25.887429+00:00"
    decision_at = datetime.fromisoformat("2026-10-03T00:30:00+00:00")
    training_as_of = datetime.fromisoformat("2026-10-03T00:31:00+00:00")
    receipt = {
        "schema_version": (
            "integration-consistent-sqlite-snapshot.v2"
            if wal_absent
            else "integration-consistent-sqlite-snapshot.v1"
        ),
        "status": "consistent_snapshot_created",
        "started_at": "2026-10-03T00:22:24.800625+00:00",
        "completed_at": completed_at,
        "source_database_path": str(source.resolve()),
        "source_observation": {
            "database": _pin(source),
            "wal": (
                {"path": str(wal.absolute()), "status": "absent", "present": False}
                if wal_absent
                else _pin(wal)
            ),
            "revision_namespace_files": namespace_files,
        },
        "source_generation_before": 2,
        "source_generation_after": 2,
        **(
            {
                "source_journal_mode_before": "wal",
                "source_journal_mode_after": "wal",
                "source_journal_mode_reader": "sqlite_file_header_read_write_version.v1",
            }
            if wal_absent
            else {}
        ),
        "snapshot": _pin(snapshot),
        "snapshot_quick_check": "ok",
        "consistency": "sqlite_backup_from_single_query_only_read_transaction",
        "source_and_revision_bytes_unchanged": True,
    }
    receipt_path = root / "snapshot_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    snapshot_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()

    namespaces = [item.value for item in SourceEvidenceNamespaceV1]
    evidence_digest = "a" * 64
    excluded_namespace = SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION.value
    dependency_path = namespace_paths[excluded_namespace]
    dependency_stat = dependency_path.stat()
    dependencies = [
        {
            "namespace": excluded_namespace,
            "role_id": "evidence",
            "path": str(dependency_path.resolve()),
            "bytes": dependency_stat.st_size,
            "mtime_ns": dependency_stat.st_mtime_ns,
            "sha256": namespace_hashes[excluded_namespace],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    dependency_canonical = json.dumps(
        dependencies,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    summary = {
        "database_path": str(source.resolve()),
        "decision_date": "2026-10-03",
        "current_restated_research": True,
        "formal_historical_PIT": False,
        "source_revision_evidence_sha256": evidence_digest,
        "source_revision_evidence": {
            "schema_version": "validated-source-evidence.v1",
            "scope_id": "ml_daily_price_revision_gate.v1",
            "cutoff_date": "2026-10-03",
            "digest_sha256": evidence_digest,
            "namespaces": [
                {
                    "namespace": namespace,
                    "presence": "present",
                    "files": [
                        {
                            "role_id": "evidence",
                            "sha256": namespace_hashes[namespace],
                        }
                    ],
                }
                for namespace in namespaces
            ],
        },
        "validated_revision_dependencies": dependencies,
        "validated_revision_dependencies_sha256": hashlib.sha256(
            dependency_canonical
        ).hexdigest(),
    }
    monkeypatch.setattr(
        gate,
        "check_daily_price_source_revision",
        lambda **_: summary,
    )
    monkeypatch.setattr(gate, "_test_source_context_summary", summary, raising=False)
    return (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    )


def _replace_receipt_wal_pin(receipt_path: Path, wal_path: Path) -> str:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source_observation"]["wal"] = _pin(wal_path)
    receipt_bytes = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    return hashlib.sha256(receipt_bytes).hexdigest()


def test_source_context_binds_snapshot_original_db_and_namespace_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)

    context = gate.load_verified_current_restated_source_context(
        snapshot,
        receipt_path,
        expected_snapshot_database_sha256=snapshot_sha,
        expected_snapshot_receipt_sha256=receipt_sha,
        original_database_path=source,
        decision_at=decision_at,
        training_as_of=training_as_of,
    )

    assert context.source_database_path == str(source.resolve())
    assert context.snapshot_database_path == str(snapshot.resolve())
    assert context.source_observed_at == datetime.fromisoformat(
        "2026-10-03T00:23:25.887429+00:00"
    )
    assert len(context.revision_namespace_files) == 4
    assert len(context.revision_dependency_files) == 1
    assert context.revision_dependency_files[0].role_id == "evidence"
    assert context.revision_dependencies_verified_at.tzinfo is not None
    assert context.revision_dependency_bundle_sha256.startswith("sha256:")
    assert context.historical_pit_eligible is False
    assert context.current_restated is True


def test_source_context_accepts_mtime_drift_only_for_pinned_empty_present_wal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    wal_path = source.with_name(source.name + "-wal")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    wal_pin = receipt["source_observation"]["wal"]
    assert wal_pin["path"] == str(wal_path.resolve())
    assert wal_pin["bytes"] == 0
    assert wal_pin["sha256"] == hashlib.sha256(b"").hexdigest()

    live_info = wal_path.stat()
    os.utime(
        wal_path,
        ns=(live_info.st_atime_ns, int(wal_pin["mtime_ns"]) + 1_000_000_000),
    )
    assert wal_path.stat().st_mtime_ns != wal_pin["mtime_ns"]

    context = gate.load_verified_current_restated_source_context(
        snapshot,
        receipt_path,
        expected_snapshot_database_sha256=snapshot_sha,
        expected_snapshot_receipt_sha256=receipt_sha,
        original_database_path=source,
        decision_at=decision_at,
        training_as_of=training_as_of,
    )

    assert context.source_wal_present is True
    assert context.source_wal_sha256 == "sha256:" + hashlib.sha256(b"").hexdigest()


def test_source_context_rejects_bytes_added_to_pinned_empty_wal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    wal_path = source.with_name(source.name + "-wal")
    wal_path.write_bytes(b"unexpected WAL bytes")

    with pytest.raises(ValueError, match="source WAL byte length differs from its receipt pin"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_keeps_nonempty_wal_mtime_pin_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        _receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    wal_path = source.with_name(source.name + "-wal")
    wal_path.write_bytes(b"pinned nonempty WAL")
    receipt_sha = _replace_receipt_wal_pin(receipt_path, wal_path)
    wal_pin = json.loads(receipt_path.read_text(encoding="utf-8"))["source_observation"]["wal"]
    live_info = wal_path.stat()
    os.utime(
        wal_path,
        ns=(live_info.st_atime_ns, int(wal_pin["mtime_ns"]) + 1_000_000_000),
    )

    with pytest.raises(ValueError, match="source WAL modification timestamp differs from its receipt pin"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_keeps_nonempty_wal_hash_pin_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        _receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    wal_path = source.with_name(source.name + "-wal")
    wal_path.write_bytes(b"pinned nonempty WAL")
    receipt_sha = _replace_receipt_wal_pin(receipt_path, wal_path)
    wal_pin = json.loads(receipt_path.read_text(encoding="utf-8"))["source_observation"]["wal"]
    wal_path.write_bytes(b"changed WAL value!!")
    os.utime(
        wal_path,
        ns=(wal_path.stat().st_atime_ns, int(wal_pin["mtime_ns"])),
    )

    with pytest.raises(ValueError, match="source WAL actual-bytes SHA-256 differs from its receipt pin"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_rejects_original_database_change_with_empty_wal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    with source.open("ab") as stream:
        stream.write(b"changed source DB")

    with pytest.raises(ValueError, match="original source database byte length differs from its receipt pin"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_rejects_wal_change_during_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    wal_path = source.with_name(source.name + "-wal")
    original_open = Path.open
    changed = False

    class _TouchAfterRead:
        def __init__(self, stream):
            self._stream = stream

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, *args):
            return self._stream.__exit__(*args)

        def read(self, size: int = -1):
            nonlocal changed
            value = self._stream.read(size)
            if not changed:
                info = wal_path.stat()
                os.utime(
                    wal_path,
                    ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000),
                )
                changed = True
            return value

    def _open_with_wal_touch(path: Path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.resolve(strict=True) == wal_path.resolve(strict=True):
            return _TouchAfterRead(stream)
        return stream

    monkeypatch.setattr(Path, "open", _open_with_wal_touch)
    with pytest.raises(ValueError, match="source WAL changed while hashing"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_accepts_explicit_absent_wal_without_creating_a_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, receipt_path, source, snapshot_sha, receipt_sha, decision_at, training_as_of = (
        _context_inputs(tmp_path, monkeypatch, wal_absent=True)
    )
    wal_path = source.with_name(source.name + "-wal")
    assert not wal_path.exists()

    context = gate.load_verified_current_restated_source_context(
        snapshot,
        receipt_path,
        expected_snapshot_database_sha256=snapshot_sha,
        expected_snapshot_receipt_sha256=receipt_sha,
        original_database_path=source,
        decision_at=decision_at,
        training_as_of=training_as_of,
    )

    assert context.source_wal_present is False
    assert context.source_wal_sha256 is None
    assert context.source_wal_path == str(wal_path.absolute())
    assert not wal_path.exists()


def test_source_context_rejects_wal_creation_after_absent_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, receipt_path, source, snapshot_sha, receipt_sha, decision_at, training_as_of = (
        _context_inputs(tmp_path, monkeypatch, wal_absent=True)
    )
    wal_path = source.with_name(source.name + "-wal")
    wal_path.write_bytes(b"appeared after snapshot")

    with pytest.raises(ValueError, match="required to remain absent"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_snapshot_v1_remains_strict_when_its_pinned_wal_disappears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, receipt_path, source, snapshot_sha, receipt_sha, decision_at, training_as_of = (
        _context_inputs(tmp_path, monkeypatch)
    )
    source.with_name(source.name + "-wal").unlink()

    with pytest.raises(ValueError, match="source WAL path cannot be resolved"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_rejects_naive_time_and_namespace_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="explicit timezone"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=datetime(2026, 10, 3, 0, 30),
            training_as_of=training_as_of,
        )

    namespace_file = (
        tmp_path
        / "data"
        / gate.REPAIR_RECEIPT_RELATIVE_DIR
        / "evidence.bin"
    )
    namespace_file.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="differs from its receipt pin"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_rejects_unpinned_file_in_namespace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    extra_file = (
        tmp_path
        / "data"
        / formal_market_revision.RECEIPT_DIR
        / "unlisted.bin"
    )
    extra_file.write_bytes(b"not in snapshot namespace pins")

    with pytest.raises(ValueError, match="complete required-root inventory"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )


def test_source_context_rejects_wrong_physical_dependency_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        snapshot,
        receipt_path,
        source,
        snapshot_sha,
        receipt_sha,
        decision_at,
        training_as_of,
    ) = _context_inputs(tmp_path, monkeypatch)
    # The excluded role must map to its actual physical dependency, not a
    # different namespace file that happens to have an independent valid pin.
    excluded_path = (
        tmp_path
        / "data"
        / excluded_daily_price_revision.RECEIPT_DIR
        / "evidence.bin"
    )
    duplicate_path = tmp_path / "data" / "unverified-copy" / "evidence.bin"
    duplicate_path.parent.mkdir(parents=True)
    duplicate_path.write_bytes(excluded_path.read_bytes())
    assert excluded_path.exists()
    # Replace only the mock summary returned by the current fixture.
    bad_summary = json.loads(json.dumps(gate._test_source_context_summary))
    bad_summary["validated_revision_dependencies"][0]["path"] = str(
        duplicate_path.resolve()
    )
    monkeypatch.setattr(gate, "check_daily_price_source_revision", lambda **_: bad_summary)
    with pytest.raises(ValueError, match="dependency digest is inconsistent"):
        gate.load_verified_current_restated_source_context(
            snapshot,
            receipt_path,
            expected_snapshot_database_sha256=snapshot_sha,
            expected_snapshot_receipt_sha256=receipt_sha,
            original_database_path=source,
            decision_at=decision_at,
            training_as_of=training_as_of,
        )
