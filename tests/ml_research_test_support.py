"""研究候選測試用的一致 snapshot 與 current-restated source context。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from data_module.contracts.source_revision import (
    SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
    ValidatedSourceEvidenceV1,
)
from data_module import excluded_daily_price_revision, formal_market_revision, historical_session_revision
import data_module.ml_daily_price_revision_gate as revision_gate


def _pin(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def write_snapshot_context_receipt(
    snapshot_database_path: Path,
    root: Path,
    *,
    completed_at: str,
    wal_absent: bool = False,
) -> tuple[Path, str]:
    """建立 integration receipt 同形的 synthetic source context。"""
    source_root = root / "source_context"
    source_root.mkdir(parents=True, exist_ok=True)
    source_database_path = source_root / "original_source.sqlite"
    source_wal_path = source_root / "original_source.sqlite-wal"
    if not source_database_path.exists():
        source_database_path.write_bytes(b"synthetic original source database")
    if not wal_absent and not source_wal_path.exists():
        source_wal_path.write_bytes(b"")
    if wal_absent and source_wal_path.exists():
        raise ValueError("absent-WAL fixture must not start with a WAL file")

    namespace_roots = {
        SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT: source_root / revision_gate.REPAIR_RECEIPT_RELATIVE_DIR,
        SourceEvidenceNamespaceV1.MARKET_REVISION: source_root / formal_market_revision.RECEIPT_DIR,
        SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION: source_root / historical_session_revision.RECEIPT_DIR,
        SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION: source_root / excluded_daily_price_revision.RECEIPT_DIR,
    }
    namespace_files: list[dict[str, object]] = []
    for namespace, namespace_root in namespace_roots.items():
        namespace_root.mkdir(parents=True, exist_ok=True)
        path = namespace_root / "evidence.json"
        if not path.exists():
            path.write_bytes(f"synthetic evidence for {namespace.value}".encode("ascii"))
        namespace_files.append(_pin(path))

    completed = datetime.fromisoformat(completed_at)
    if completed.tzinfo is None or completed.utcoffset() is None:
        raise ValueError("completed_at must include a timezone")
    started = completed - timedelta(seconds=60)
    payload = {
        "schema_version": (
            "integration-consistent-sqlite-snapshot.v2"
            if wal_absent
            else "integration-consistent-sqlite-snapshot.v1"
        ),
        "status": "consistent_snapshot_created",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "source_database_path": str(source_database_path.resolve()),
        "source_observation": {
            "database": _pin(source_database_path),
            "wal": (
                {
                    "path": str(source_wal_path.absolute()),
                    "status": "absent",
                    "present": False,
                }
                if wal_absent
                else _pin(source_wal_path)
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
        "snapshot": _pin(snapshot_database_path),
        "snapshot_quick_check": "ok",
        "consistency": "sqlite_backup_from_single_query_only_read_transaction",
        "source_and_revision_bytes_unchanged": True,
        "revision_custody_qualification": "requires_separate_strict_inspection",
    }
    receipt_path = root / "snapshot_receipt.json"
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return receipt_path, "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()


def install_test_revision_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """替換四 namespace gate 的合成結果；A loader 仍執行真實 bytes/clock 驗證。"""

    def check_daily_price_source_revision(
        *, database_path: Path, decision_date: object, allow_source_revision_research: bool = False
    ) -> dict[str, object]:
        del allow_source_revision_research
        data_root = Path(database_path).resolve().parent
        namespace_roots = {
            SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT: data_root / revision_gate.REPAIR_RECEIPT_RELATIVE_DIR,
            SourceEvidenceNamespaceV1.MARKET_REVISION: data_root / formal_market_revision.RECEIPT_DIR,
            SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION: data_root / historical_session_revision.RECEIPT_DIR,
            SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION: data_root / excluded_daily_price_revision.RECEIPT_DIR,
        }
        evidence_namespaces = []
        evidence_payload_namespaces = []
        for namespace in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1:
            evidence_path = namespace_roots[namespace] / "evidence.json"
            evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            namespace_evidence = ValidatedNamespaceEvidenceV1(
                namespace=namespace,
                presence=SourceEvidencePresenceV1.PRESENT,
                files=(ValidatedEvidenceFileV1(role_id="evidence", sha256=evidence_sha),),
            )
            evidence_namespaces.append(namespace_evidence)
            evidence_payload_namespaces.append({
                "namespace": namespace.value,
                "presence": "present",
                "digest_sha256": namespace_evidence.digest_sha256,
                "files": [{"role_id": "evidence", "sha256": evidence_sha}],
            })
        cutoff = date.fromisoformat(str(decision_date))
        evidence = ValidatedSourceEvidenceV1(
            schema_version=SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
            scope_id="b-test-source-context",
            cutoff_date=cutoff,
            namespaces=tuple(evidence_namespaces),
        )
        digest = evidence.digest_sha256
        excluded_namespace = SourceEvidenceNamespaceV1.EXCLUDED_DAILY_PRICE_REVISION
        dependency_path = namespace_roots[excluded_namespace] / "evidence.json"
        dependency_stat = dependency_path.stat()
        revision_dependencies = [
            {
                "namespace": excluded_namespace.value,
                "role_id": "evidence",
                "path": str(dependency_path.resolve()),
                "bytes": dependency_stat.st_size,
                "mtime_ns": dependency_stat.st_mtime_ns,
                "sha256": hashlib.sha256(dependency_path.read_bytes()).hexdigest(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        dependency_bytes = json.dumps(
            revision_dependencies,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        typed_evidence = {
            "schema_version": SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
            "scope_id": "b-test-source-context",
            "cutoff_date": cutoff.isoformat(),
            "digest_sha256": digest,
            "namespaces": evidence_payload_namespaces,
        }
        return {
            "database_path": str(Path(database_path).resolve()),
            "decision_date": str(decision_date),
            "current_restated_research": True,
            "formal_historical_PIT": False,
            "source_revision_evidence_sha256": digest,
            "source_revision_evidence": typed_evidence,
            "validated_revision_dependencies": revision_dependencies,
            "validated_revision_dependencies_sha256": hashlib.sha256(
                dependency_bytes
            ).hexdigest(),
        }

    monkeypatch.setattr(revision_gate, "check_daily_price_source_revision", check_daily_price_source_revision)
