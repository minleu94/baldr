"""Bounded governance recognizes COW audit metadata and both retained databases."""
from pathlib import Path
import json
import pytest

from app_module.research_snapshot_storage_governance import diagnose_research_snapshot_storage
from tests.test_f4_item_revision_storage_recovery import _create_legacy_v2, _item, _payload


def _prepared(tmp_path: Path, *, external_target: bool = False) -> tuple[Path, Path, Path]:
    from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite
    from app_module.watchlist_cow_activation import activate_watchlist_sqlite
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    source = tmp_path / "watchlist" / "watchlists.db"
    target = source.with_name("watchlists.v3-cow.sqlite")
    if external_target:
        target = tmp_path / "independent" / "watchlists.v3-cow.sqlite"
        target.parent.mkdir()
    _create_legacy_v2(source, _payload([_item("2330", "manual", "origin")]))
    assert convert_watchlist_sqlite(source, target)["status"] == "ready"
    assert activate_watchlist_sqlite(source, target)["status"] == "activated"
    return snapshots, source, target


def _diagnose(snapshots: Path, source: Path) -> dict:
    return diagnose_research_snapshot_storage(
        snapshots, watchlist_dir=source.parent, watchlist_inventory_complete=True,
    )


@pytest.mark.parametrize("external_target", [False, True])
def test_cow_governance_retained_source_and_active_target(tmp_path: Path, external_target: bool) -> None:
    snapshots, source, target = _prepared(tmp_path, external_target=external_target)
    before = (source.read_bytes(), target.read_bytes())
    result = _diagnose(snapshots, source)
    assert result["storage"]["scan_complete"] is True, result["issues"]
    assert result["storage"]["references_complete"] is True, result["issues"]
    assert (source.read_bytes(), target.read_bytes()) == before


def test_cow_governance_target_append_and_rollback(tmp_path: Path) -> None:
    from data_module.watchlist_repository import WatchlistRepository
    from app_module.watchlist_cow_activation import rollback_watchlist_sqlite
    snapshots, source, target = _prepared(tmp_path)
    original = source.read_bytes()
    repository = WatchlistRepository(target)
    payload, revision = repository.load("default")
    payload["items"].append(_item("2454", "manual", "post-activation"))
    repository.save("default", payload, expected_revision=revision)
    active = _diagnose(snapshots, source)
    assert active["storage"]["references_complete"] is True, active["issues"]
    assert rollback_watchlist_sqlite(source)["status"] == "rolled_back"
    restored = _diagnose(snapshots, source)
    assert restored["storage"]["references_complete"] is True, restored["issues"]
    assert source.read_bytes() == original
    assert repository.load("default")[1] == revision + 1


@pytest.mark.parametrize("fault", ["receipt_hash", "lineage_shape"])
def test_cow_governance_marker_receipt_binding_fails_closed(tmp_path: Path, fault: str) -> None:
    snapshots, source, target = _prepared(tmp_path)
    original = (source.read_bytes(), target.read_bytes())
    marker = Path(f"{source}.cow-active.json")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if fault == "receipt_hash":
        payload["receipt_sha256"] = "0" * 64
    else:
        payload["target_base_lineage"] = {"default": "invalid"}
    marker.write_text(json.dumps(payload), encoding="utf-8")
    result = _diagnose(snapshots, source)
    assert result["storage"]["references_complete"] is False
    assert result["issues"]
    assert (source.read_bytes(), target.read_bytes()) == original


def test_cow_governance_audit_changed_during_scan_is_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_module import research_snapshot_storage_governance as governance
    snapshots, source, target = _prepared(tmp_path)
    original = (source.read_bytes(), target.read_bytes())
    scan = governance._scan_watchlist_db
    marker = Path(f"{source}.cow-active.json")

    def changed(*args: object, **kwargs: object) -> object:
        result = scan(*args, **kwargs)
        marker.write_bytes(marker.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(governance, "_scan_watchlist_db", changed)
    result = _diagnose(snapshots, source)
    assert result["storage"]["references_complete"] is False
    assert any(issue["code"] == "watchlist_cow_changed_during_scan" for issue in result["issues"])
    assert (source.read_bytes(), target.read_bytes()) == original


@pytest.mark.parametrize("external_target", [False, True])
def test_json_cow_governance_retains_json_and_target_after_append_rollback(
    tmp_path: Path, external_target: bool
) -> None:
    from data_module.watchlist_json_cow import convert_watchlist_json
    from app_module.watchlist_cow_activation import activate_watchlist_sqlite, rollback_watchlist_sqlite
    from data_module.watchlist_repository import WatchlistRepository

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    source = tmp_path / "watchlist" / "default.json"
    source.parent.mkdir()
    target = source.with_name("watchlists.v3-cow.sqlite")
    if external_target:
        target = tmp_path / "independent" / "watchlists.v3-cow.sqlite"
        target.parent.mkdir()
    payload = _payload([_item("2330", "manual", "original", notes="保留收藏理由")])
    payload["opaque_history"] = [{"date": "2026-10-01", "reason": "合成歷史"}]
    source.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    original = source.read_bytes()
    assert convert_watchlist_json(source, target)["status"] == "ready"
    assert activate_watchlist_sqlite(source, target)["status"] == "activated"
    active = _diagnose(snapshots, source)
    assert active["storage"]["references_complete"] is True, active["issues"]
    repository = WatchlistRepository(target)
    value, revision = repository.load("default")
    value["items"].append(_item("2454", "manual", "new"))
    repository.save("default", value, expected_revision=revision)
    assert rollback_watchlist_sqlite(source)["status"] == "rolled_back"
    restored = _diagnose(snapshots, source)
    assert restored["storage"]["references_complete"] is True, restored["issues"]
    assert restored["storage"]["watchlist_sources_scanned"] == 2
    assert source.read_bytes() == original
    assert repository.load("default")[1] == 2
    assert not source.with_name("watchlists.db").exists()


def test_json_cow_governance_active_source_change_fails_closed(tmp_path: Path) -> None:
    from data_module.watchlist_json_cow import convert_watchlist_json
    from app_module.watchlist_cow_activation import activate_watchlist_sqlite

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    source = tmp_path / "watchlist" / "default.json"
    source.parent.mkdir()
    source.write_text(json.dumps(_payload([_item("2330", "manual", "old")])), encoding="utf-8")
    target = source.with_name("watchlists.v3-cow.sqlite")
    assert convert_watchlist_json(source, target)["status"] == "ready"
    assert activate_watchlist_sqlite(source, target)["status"] == "activated"
    source.write_bytes(source.read_bytes() + b"\n")
    result = _diagnose(snapshots, source)
    assert result["storage"]["references_complete"] is False
    assert any(issue["code"] == "watchlist_cow_source_hash_mismatch" for issue in result["issues"])
