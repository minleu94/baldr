"""研究快照儲存盤點首版的 fail-closed 與 bytes 預算測試。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app_module import research_snapshot_storage_governance as governance
from app_module.daily_market_feature_snapshot import DAILY_MARKET_FEATURE_CONTRACT_VERSION
from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _feature_object() -> dict[str, object]:
    return {
        "conditions": {},
        "contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "decision_date": "2026-10-05",
        "features": {},
        "input_fingerprint_sha256": "a" * 64,
        "market_date": "2026-10-05",
        "method_contracts": method_contracts_payload(),
        "method_contracts_sha256": method_contracts_sha256(),
        "policy": {},
        "scope_identity": "scope",
        "snapshot_identity_sha256": "c" * 64,
        "stock_code": "2330",
    }


def test_missing_snapshot_root_fails_closed_and_never_enables_delete(tmp_path: Path) -> None:
    receipt = governance.diagnose_research_snapshot_storage(tmp_path / "missing")

    assert receipt["storage"]["scan_complete"] is False
    assert receipt["storage"]["references_complete"] is False
    assert receipt["storage"]["retained_bytes_complete"] is False
    assert receipt["dry_run_candidates"] == []
    assert receipt["policy"]["permanent_delete_enabled"] is False
    assert receipt["policy"]["cleanup_authorized"] is False
    assert receipt["automatic_action"] == "none"


def test_orphan_feature_object_is_candidate_only_with_complete_explicit_watchlists(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    objects = root / "objects"
    objects.mkdir(parents=True)
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    raw = _canonical(_feature_object())
    digest = hashlib.sha256(raw).hexdigest()
    (objects / f"{digest}.json").write_bytes(raw)

    receipt = governance.diagnose_research_snapshot_storage(
        root, watchlist_dir=watchlists, watchlist_inventory_complete=True
    )

    assert receipt["storage"]["scan_complete"] is True
    assert receipt["storage"]["references_complete"] is True
    assert len(receipt["dry_run_candidates"]) == 1
    candidate = receipt["dry_run_candidates"][0]
    assert candidate["reason"] == "unreferenced_feature_object"
    assert candidate["dry_run_only"] is True
    assert candidate["requires_user_approval_each_time"] is True
    assert candidate["automatic_action"] == "none"


def test_missing_watchlist_inventory_blocks_all_candidates(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    objects = root / "objects"
    objects.mkdir(parents=True)
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    raw = _canonical(_feature_object())
    digest = hashlib.sha256(raw).hexdigest()
    (objects / f"{digest}.json").write_bytes(raw)

    receipt = governance.diagnose_research_snapshot_storage(root, watchlist_dir=watchlists)

    assert receipt["storage"]["scan_complete"] is True
    assert receipt["storage"]["references_complete"] is False
    assert receipt["dry_run_candidates"] == []


def test_unknown_feature_contract_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    objects = root / "objects"
    objects.mkdir(parents=True)
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    payload = _feature_object()
    payload["contract_version"] = "unknown.v99"
    raw = _canonical(payload)
    digest = hashlib.sha256(raw).hexdigest()
    (objects / f"{digest}.json").write_bytes(raw)

    receipt = governance.diagnose_research_snapshot_storage(root, watchlist_dir=watchlists)

    assert receipt["storage"]["scan_complete"] is False
    assert receipt["dry_run_candidates"] == []
    assert receipt["growth"]["forecast_status"] == "incomplete_inventory"
    assert receipt["growth"]["forecast_bytes"] is None


def test_preflight_uses_bounded_byte_inputs_without_walking_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []

    def fake_usage(path: Path) -> dict[str, int | str]:
        calls.append(Path(path))
        return {"probe_path": str(path), "total_bytes": 100 * 1024**3,
                "used_bytes": 10 * 1024**3, "free_bytes": 90 * 1024**3}

    monkeypatch.setattr(governance, "filesystem_usage", fake_usage)
    result = governance.preflight_research_snapshot_publication(
        output_root=tmp_path / "persistent",
        persistent_existing_bytes=32 * 1024 * 1024,
        persistent_new_bytes=0,
        temporary_peak_bytes=0,
    )

    assert len(calls) == 1
    assert result["persistent_existing_bytes_observed"] == 32 * 1024 * 1024
    assert result["temporary_peak_bytes_observed"] == 0
    assert result["central_reserve_bytes"] == result["safety_reserve_bytes"]


def test_preflight_checks_a_distinct_temporary_root_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []

    def fake_usage(path: Path) -> dict[str, int | str]:
        calls.append(Path(path))
        return {"probe_path": str(path), "total_bytes": 100 * 1024**3,
                "used_bytes": 10 * 1024**3, "free_bytes": 90 * 1024**3}

    monkeypatch.setattr(governance, "filesystem_usage", fake_usage)
    result = governance.preflight_research_snapshot_publication(
        output_root=tmp_path / "persistent",
        temporary_root=tmp_path / "temporary",
        persistent_existing_bytes=24 * 1024 * 1024,
        persistent_new_bytes=1,
        temporary_peak_bytes=1,
    )

    assert len(calls) == 2
    assert len(result["filesystem_checks"]) == 2
    assert all(check["persistent_existing_bytes"] == 24 * 1024 * 1024 for check in result["filesystem_checks"])
    assert all(check["temporary_peak_bytes_observed"] == 1 for check in result["filesystem_checks"])


def test_preflight_rejects_growth_above_existing_writer_bound(tmp_path: Path) -> None:
    with pytest.raises(governance.StorageGovernanceError, match="8 MiB"):
        governance.preflight_research_snapshot_publication(
            output_root=tmp_path,
            persistent_existing_bytes=0,
            persistent_new_bytes=governance.MAX_BATCH_NEW_BYTES + 1,
            temporary_peak_bytes=0,
        )


def test_watchlist_sqlite_is_opened_immutable_and_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    root.mkdir()
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    db = watchlists / "watchlists.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE watchlists (
                watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, revision INTEGER NOT NULL,
                source_hash TEXT NOT NULL DEFAULT '', is_deleted INTEGER NOT NULL DEFAULT 0,
                last_revision_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE watchlist_revisions (
                revision_id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, revision INTEGER NOT NULL,
                operation TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                source_hash TEXT NOT NULL DEFAULT '', identity_status TEXT NOT NULL DEFAULT 'unknown',
                continuity_event_id TEXT NOT NULL DEFAULT '', revision_of TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
    before = db.stat()

    receipt = governance.diagnose_research_snapshot_storage(
        root, watchlist_dir=watchlists, watchlist_inventory_complete=True
    )

    after = db.stat()
    assert receipt["storage"]["references_complete"] is True
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino)
    assert not Path(f"{db}-wal").exists()
    assert not Path(f"{db}-shm").exists()


def test_unknown_watchlist_subdirectory_blocks_reference_completeness(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    root.mkdir()
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    (watchlists / "unknown-source").mkdir()

    receipt = governance.diagnose_research_snapshot_storage(
        root, watchlist_dir=watchlists, watchlist_inventory_complete=True
    )

    assert receipt["storage"]["scan_complete"] is True
    assert receipt["storage"]["references_complete"] is False
    assert any(issue["code"] == "watchlist_source_schema_unknown" for issue in receipt["issues"])


def test_watchlist_directory_entry_budget_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "snapshots"
    root.mkdir()
    watchlists = tmp_path / "watchlists"
    watchlists.mkdir()
    (watchlists / "one.json").write_text("{}", encoding="utf-8")
    (watchlists / "two.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(governance, "MAX_RETAINED_ENTRIES", 1)

    receipt = governance.diagnose_research_snapshot_storage(
        root, watchlist_dir=watchlists, watchlist_inventory_complete=True
    )

    assert receipt["storage"]["references_complete"] is False
    assert any(issue["code"] == "scan_entry_budget_exceeded" for issue in receipt["issues"])


def test_windows_reparse_point_flag_is_recognized() -> None:
    from types import SimpleNamespace

    assert governance._is_reparse_stat(SimpleNamespace(st_file_attributes=0x400)) is True
