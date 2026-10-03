from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

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
) -> tuple[Path, Path, Path, str, str, datetime, datetime]:
    source = root / "data" / "twstock.db"
    snapshot = root / "output" / "ml_research" / "snapshot.sqlite"
    wal = root / "data" / "twstock.db-wal"
    source.parent.mkdir(parents=True)
    snapshot.parent.mkdir(parents=True)
    source.write_bytes(b"source database bytes")
    snapshot.write_bytes(b"consistent snapshot bytes")
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
        "schema_version": "integration-consistent-sqlite-snapshot.v1",
        "status": "consistent_snapshot_created",
        "started_at": "2026-10-03T00:22:24.800625+00:00",
        "completed_at": completed_at,
        "source_database_path": str(source.resolve()),
        "source_observation": {
            "database": _pin(source),
            "wal": _pin(wal),
            "revision_namespace_files": namespace_files,
        },
        "source_generation_before": 2,
        "source_generation_after": 2,
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
