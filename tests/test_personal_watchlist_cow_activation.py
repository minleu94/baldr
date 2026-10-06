"""集中個人控制平面的 fixture 啟用／重開／保存／回復與拒絕。"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app_module.personal_data_paths import WatchlistCowControlPaths, resolve_personal_data_paths
from app_module.watchlist_cow_activation import (
    PERSONAL_ACTIVATION_SCHEMA, PersonalWatchlistCowService, WatchlistCowActivationError,
    activate_watchlist_sqlite, preview_watchlist_sqlite_activation,
    resolve_watchlist_sqlite_activation, rollback_watchlist_sqlite,
)
from data_module.watchlist_json_cow import convert_watchlist_json
from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite
from test_watchlist_cow_activation import _build_source


def setup_controls(tmp_path, kind):
    market = tmp_path / "FA_Data"
    source = market / "output" / "watchlist" / ("default.json" if kind == "json" else "watchlists.db")
    source.parent.mkdir(parents=True)
    if kind == "json":
        source.write_text(json.dumps({"version": 1, "name": "fixture", "items": [{
            "stock_code": "2330", "stock_name": "fixture", "added_at": "2026-10-01T09:00:00",
            "source": "manual", "notes": "synthetic", "tags": [],
        }], "created_at": "2026-10-01T09:00:00", "updated_at": "2026-10-01T09:00:00"}), encoding="utf-8")
    else:
        _build_source(source, int(kind))
    paths = resolve_personal_data_paths(market, personal_root=tmp_path / "personal", environ={})
    return WatchlistCowControlPaths(paths, source)


def source_manifest(controls):
    return {str(p.relative_to(controls.personal_paths.market_root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in controls.personal_paths.market_root.rglob("*") if p.is_file()}


def convert(controls, kind):
    converter = convert_watchlist_json if kind == "json" else convert_watchlist_sqlite
    result = converter(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    assert result["status"] == "ready", result
    return result


@pytest.mark.parametrize("kind", ["json", "1", "2"])
def test_personal_convert_activate_reopen_append_rollback_preserves_market(tmp_path, kind):
    controls = setup_controls(tmp_path, kind)
    before = source_manifest(controls)
    convert(controls, kind)
    assert source_manifest(controls) == before
    assert preview_watchlist_sqlite_activation(controls.source_path, controls.personal_paths.watchlist_db,
                                              control_paths=controls)["status"] == "ready"
    activated = activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db,
                                        control_paths=controls)
    assert activated["status"] == "activated"
    marker = json.loads(controls.marker_path.read_text(encoding="utf-8"))
    assert marker["schema_version"] == PERSONAL_ACTIVATION_SCHEMA
    assert Path(marker["backup_marker_path"]).is_relative_to(controls.personal_paths.personal_root)
    assert Path(marker["receipt_path"]) == controls.receipt_path
    if kind == "json":
        assert controls.source_backup_path.read_bytes() == controls.source_path.read_bytes()
    assert not controls.lock_path.exists()
    fresh = PersonalWatchlistCowService(controls)
    loaded = fresh.load("default")
    assert loaded is not None
    payload, revision = loaded
    # 在另一個背景程序重建control契約與service後追加，驗真正restart讀回。
    child_code = """
import sys
from pathlib import Path
from app_module.personal_data_paths import resolve_personal_data_paths, WatchlistCowControlPaths
from app_module.watchlist_cow_activation import PersonalWatchlistCowService
paths = resolve_personal_data_paths(sys.argv[1], personal_root=sys.argv[2], environ={})
service = PersonalWatchlistCowService(WatchlistCowControlPaths(paths, Path(sys.argv[3])))
payload, revision = service.load("default")
payload["items"].append({"stock_code": "2317", "stock_name": "synthetic", "source": "manual",
                        "added_at": "2026-10-05T09:00:00", "tags": [], "notes": "fixture"})
service.save("default", payload, expected_revision=revision)
print("personal-child-save-ok")
"""
    child = subprocess.run(
        [sys.executable, "-c", child_code, str(controls.personal_paths.market_root),
         str(controls.personal_paths.personal_root), str(controls.source_path)],
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert child.returncode == 0, child.stderr
    assert "personal-child-save-ok" in child.stdout
    reopened = PersonalWatchlistCowService(controls)
    assert len(reopened.load("default")[0]["items"]) == 2
    target_before_rollback = controls.personal_paths.watchlist_db.read_bytes()
    rolled = rollback_watchlist_sqlite(controls.source_path, control_paths=controls)
    assert rolled["status"] == "rolled_back"
    assert source_manifest(controls) == before
    assert controls.personal_paths.watchlist_db.read_bytes() == target_before_rollback
    with pytest.raises(WatchlistCowActivationError, match="personal_writer_disabled"):
        PersonalWatchlistCowService(controls)
    with pytest.raises(WatchlistCowActivationError, match="personal_writer_disabled"):
        fresh.save("default", payload, expected_revision=revision + 1)
    assert source_manifest(controls) == before
    assert not controls.lock_path.exists()
    assert resolve_watchlist_sqlite_activation(controls.personal_paths.watchlist_db)["status"] == "blocked"
    for p in controls.personal_paths.personal_root.rglob("*"):
        if p.is_file():
            controls.assert_personal(p)


def test_missing_personal_activation_does_not_create_source_control_files(tmp_path):
    controls = setup_controls(tmp_path, "json")
    before = source_manifest(controls)
    assert resolve_watchlist_sqlite_activation(controls.source_path, control_paths=controls)["status"] == "inactive"
    assert not controls.personal_paths.personal_root.exists()
    assert source_manifest(controls) == before


@pytest.mark.parametrize("field", ["receipt_path", "backup_marker_path", "target_path"])
def test_source_side_control_pointer_is_rejected(tmp_path, field):
    controls = setup_controls(tmp_path, "json")
    before = source_manifest(controls)
    convert(controls, "json")
    activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    marker = json.loads(controls.marker_path.read_text(encoding="utf-8"))
    marker[field] = str(controls.source_path.parent / "wrong.json")
    controls.marker_path.write_text(json.dumps(marker), encoding="utf-8")
    assert resolve_watchlist_sqlite_activation(controls.source_path, control_paths=controls)["status"] == "blocked"
    with pytest.raises(WatchlistCowActivationError):
        rollback_watchlist_sqlite(controls.source_path, control_paths=controls)
    assert source_manifest(controls) == before


def test_legacy_marker_needs_review_without_move(tmp_path):
    controls = setup_controls(tmp_path, "json")
    convert(controls, "json")
    old = controls.source_path.with_name(controls.source_path.name + ".cow-active.json")
    old.write_bytes(b'{"schema_version":"legacy fixture"}')
    before = source_manifest(controls)
    result = preview_watchlist_sqlite_activation(controls.source_path, controls.personal_paths.watchlist_db,
                                                control_paths=controls)
    assert result["code"] == "legacy_control_marker_requires_review"
    assert source_manifest(controls) == before
    assert not controls.marker_path.exists()


def test_backup_corruption_blocks_reopen_and_rollback(tmp_path):
    controls = setup_controls(tmp_path, "json")
    convert(controls, "json")
    activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    controls.source_backup_path.write_bytes(b"wrong")
    result = resolve_watchlist_sqlite_activation(controls.source_path, control_paths=controls)
    assert result["status"] == "blocked"
    assert result["code"] == "source_backup_changed"
    with pytest.raises(WatchlistCowActivationError):
        rollback_watchlist_sqlite(controls.source_path, control_paths=controls)


def test_active_marker_corruption_does_not_fallback_or_touch_source(tmp_path):
    controls = setup_controls(tmp_path, "json")
    before = source_manifest(controls)
    convert(controls, "json")
    activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    controls.marker_path.write_bytes(b"wrong")
    with pytest.raises(WatchlistCowActivationError, match="personal_writer_disabled"):
        PersonalWatchlistCowService(controls)
    assert source_manifest(controls) == before


def test_control_root_junction_swap_blocks_rollback(tmp_path):
    controls = setup_controls(tmp_path, "json")
    convert(controls, "json")
    activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    original = controls.personal_paths.personal_root
    moved = tmp_path / "moved_personal"
    original.rename(moved)
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(original), str(moved)],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0
    else:
        original.symlink_to(moved, target_is_directory=True)
    result = resolve_watchlist_sqlite_activation(controls.source_path, control_paths=controls)
    assert result["status"] == "blocked"
    with pytest.raises(WatchlistCowActivationError):
        rollback_watchlist_sqlite(controls.source_path, control_paths=controls)


def test_control_marker_hardlink_blocks_activation(tmp_path):
    controls = setup_controls(tmp_path, "json")
    convert(controls, "json")
    alias = controls.personal_paths.personal_root / "alias.json"
    alias.write_bytes(b"fixture")
    os.link(alias, controls.marker_path)
    assert preview_watchlist_sqlite_activation(controls.source_path, controls.personal_paths.watchlist_db,
                                              control_paths=controls)["status"] == "blocked"

def test_receipt_override_in_source_root_rejected_before_target_creation(tmp_path):
    controls = setup_controls(tmp_path, "json")
    before = source_manifest(controls)
    result = preview_watchlist_sqlite_activation(
        controls.source_path, controls.personal_paths.watchlist_db,
        receipt_path=controls.source_path.parent / "receipt.json", control_paths=controls,
    )
    assert result["status"] == "blocked"
    assert result["code"] == "control_path_outside_personal"
    assert not controls.personal_paths.personal_root.exists()
    assert source_manifest(controls) == before


def test_source_hardlink_rejected_before_activation(tmp_path):
    controls = setup_controls(tmp_path, "json")
    os.link(controls.source_path, controls.source_path.parent / "alias")
    result = preview_watchlist_sqlite_activation(
        controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls,
    )
    assert result["status"] == "blocked"
    assert result["code"] == "source_path_alias"
    assert not controls.personal_paths.personal_root.exists()


def test_overlapping_personal_root_rejected_even_manual_contract(tmp_path):
    from app_module.personal_data_paths import PersonalDataPaths
    controls = setup_controls(tmp_path, "json")
    unsafe = WatchlistCowControlPaths(PersonalDataPaths(
        controls.personal_paths.market_root, controls.personal_paths.legacy_output_root,
        controls.personal_paths.market_root / "personal",
    ), controls.source_path)
    result = preview_watchlist_sqlite_activation(
        unsafe.source_path, unsafe.personal_paths.watchlist_db, control_paths=unsafe,
    )
    assert result["status"] == "blocked"
    assert result["code"] == "overlapping_roots"
    assert not unsafe.personal_paths.personal_root.exists()

@pytest.mark.parametrize("kind", ["json", "1", "2"])
def test_rollback_does_not_allow_source_mutation_or_resume_source_writer(tmp_path, kind):
    controls = setup_controls(tmp_path, kind)
    convert(controls, kind)
    activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db, control_paths=controls)
    rollback_watchlist_sqlite(controls.source_path, control_paths=controls)
    # 故意改synthetic來源，用以證明回復後不暗中接受可變legacy writer。
    controls.source_path.write_bytes(controls.source_path.read_bytes() + b"changed-fixture")
    result = resolve_watchlist_sqlite_activation(controls.source_path, control_paths=controls)
    assert result["status"] == "blocked"
    assert result["code"] in {"source_changed", "original_source_changed"}


def test_cancelled_activation_preserves_personal_and_market_state(tmp_path):
    controls = setup_controls(tmp_path, "json")
    convert(controls, "json")
    before = source_manifest(controls)
    files_before = {str(p.relative_to(controls.personal_paths.personal_root)): p.read_bytes()
                    for p in controls.personal_paths.personal_root.rglob("*") if p.is_file()}
    with pytest.raises(WatchlistCowActivationError, match="cancelled"):
        activate_watchlist_sqlite(controls.source_path, controls.personal_paths.watchlist_db,
                                 control_paths=controls, cancel_check=lambda: True)
    files_after = {str(p.relative_to(controls.personal_paths.personal_root)): p.read_bytes()
                   for p in controls.personal_paths.personal_root.rglob("*") if p.is_file()}
    assert files_after == files_before
    assert source_manifest(controls) == before