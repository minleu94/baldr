"""全部使用 synthetic fixtures；不讀取正式 JSON／市場 DB。"""

import os
import subprocess
import sys
import hashlib
from pathlib import Path

import pytest

from app_module.personal_data_paths import (
    PersonalDataPathError,
    plan_market_only_export,
    resolve_personal_data_paths,
)


@pytest.fixture
def layout(tmp_path):
    market = tmp_path / "FA_Data"
    market.mkdir()
    personal = tmp_path / "FA_Personal"
    paths = resolve_personal_data_paths(market, personal_root=personal, environ={})
    return paths, tmp_path / "market_package"


def assert_code(code, call):
    with pytest.raises(PersonalDataPathError) as caught:
        call()
    assert caught.value.code == code


def create_market_file(paths, name="daily_price/20261002.csv"):
    path = paths.market_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"date,stock,close\n20261002,1234,100\n")
    return path


def make_directory_link(link, target):
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            pytest.skip("此執行環境無法建立 synthetic junction")
    else:
        link.symlink_to(target, target_is_directory=True)


def test_resolution_is_readonly_and_personal_artifacts_stay_outside_market(layout):
    paths, _ = layout
    assert not paths.personal_root.exists()
    for path in (paths.watchlist_db, paths.activation_marker, paths.conversion_receipt,
                 paths.backup_root, paths.marker_backup_root,
                 paths.research_notes_root, paths.ledger_root):
        assert path.is_relative_to(paths.personal_root)
        assert not path.is_relative_to(paths.market_root)
    assert paths.watchlist_db.name == "watchlists.v3.sqlite"
    assert not paths.personal_root.exists()


def test_explicit_root_precedes_environment(tmp_path):
    paths = resolve_personal_data_paths(
        tmp_path / "market", personal_root=tmp_path / "explicit",
        environ={"PERSONAL_DATA_ROOT": str(tmp_path / "env")},
    )
    assert paths.personal_root == tmp_path / "explicit"


def test_environment_root_is_opt_in(tmp_path):
    paths = resolve_personal_data_paths(
        tmp_path / "market", environ={"PERSONAL_DATA_ROOT": str(tmp_path / "personal")},
    )
    assert paths.personal_root == tmp_path / "personal"


@pytest.mark.parametrize("env", [{}, {"PERSONAL_DATA_ROOT": "  "}])
def test_no_implicit_personal_root(tmp_path, env):
    assert_code("personal_root_unconfigured", lambda: resolve_personal_data_paths(tmp_path, environ=env))


@pytest.mark.parametrize("kind", ["same", "child", "ancestor"])
def test_overlapping_roots_fail(tmp_path, kind):
    market = tmp_path / "market"
    personal = {"same": market, "child": market / "output" / "personal", "ancestor": tmp_path}[kind]
    assert_code("overlapping_roots", lambda: resolve_personal_data_paths(market, personal_root=personal))


def test_external_legacy_output_is_also_protected(tmp_path):
    assert_code("overlapping_roots", lambda: resolve_personal_data_paths(
        tmp_path / "market", personal_root=tmp_path / "external" / "personal",
        legacy_output_root=tmp_path / "external",
    ))


@pytest.mark.parametrize("bad", ["relative", "D:relative"])
def test_relative_roots_fail(tmp_path, bad):
    assert_code("absolute_path_required", lambda: resolve_personal_data_paths(tmp_path, personal_root=bad))


def test_parent_traversal_root_fails(tmp_path):
    assert_code("absolute_path_required", lambda: resolve_personal_data_paths(
        tmp_path / "market", personal_root=tmp_path / "x" / ".." / "personal",
    ))


def test_root_junction_rejected_even_when_target_disjoint(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked_personal"
    make_directory_link(link, target)
    assert_code("linked_path", lambda: resolve_personal_data_paths(tmp_path / "market", personal_root=link))


def test_personal_child_junction_swap_rejected(layout):
    paths, _ = layout
    paths.personal_root.mkdir()
    make_directory_link(paths.personal_root / "watchlists", paths.market_root)
    assert_code("linked_path", paths.validate)


@pytest.mark.parametrize("name", [
    "daily_price/20261002.csv", "daily_price_tpex/20261002.csv",
    "technical_analysis/1234.csv", "broker_flow/20261002/1234.csv",
    "meta_data/market_index.csv", "meta_data/industry_index.csv",
    "meta_data/stock_data_whole.csv", "meta_data/all_stocks_data.csv",
    "meta_data/broker_branch_registry.csv",
])
def test_fixed_market_allowlist_and_readonly_plan(layout, name):
    paths, destination = layout
    source = create_market_file(paths, name)
    before = source.read_bytes()
    plan = plan_market_only_export(paths, [name], destination_root=destination)
    plan.validate()
    assert plan.files[0].source_path == source
    assert source.read_bytes() == before
    assert not destination.exists()
    assert not paths.personal_root.exists()


@pytest.mark.parametrize("name", [
    "output/watchlist/default.json", "output/watchlist/watchlists.db",
    "sqlite/twstock.db", "meta_data/notes.csv", "logs/update.csv",
    "research_notes/notes.csv", "ledgers/holdings.csv", "daily_price/private.json",
    "daily_price/test.sqlite", "daily_price/test.db-wal", "daily_price/test.csv.cow-active.json",
    "daily_price/test.CSV", "daily_price",
])
def test_nonmarket_and_whole_db_exports_rejected(layout, name):
    paths, destination = layout
    assert_code("market_export_not_allowlisted", lambda: plan_market_only_export(paths, [name], destination_root=destination))


@pytest.mark.parametrize("name", [
    "../FA_Personal/notes.csv", "/daily_price/test.csv", "daily_price/../test.csv",
    "daily_price//test.csv", "./daily_price/test.csv", "daily_price\\test.csv",
    "daily_price/test.csv:secret", "C:/daily_price/test.csv", "",
])
def test_export_traversal_and_aliases_rejected(layout, name):
    paths, destination = layout
    assert_code("invalid_export_relative_path", lambda: plan_market_only_export(paths, [name], destination_root=destination))


@pytest.mark.parametrize("kind", ["market", "personal", "output", "ancestor"])
def test_destination_cannot_overlap_any_protected_root(layout, kind):
    paths, _ = layout
    create_market_file(paths)
    destination = {"market": paths.market_root / "package", "personal": paths.personal_root / "package",
                   "output": paths.legacy_output_root, "ancestor": paths.market_root.parent}[kind]
    assert_code("overlapping_roots", lambda: plan_market_only_export(
        paths, ["daily_price/20261002.csv"], destination_root=destination,
    ))


def test_junction_to_personal_under_whitelist_rejected(layout):
    paths, destination = layout
    paths.personal_root.mkdir()
    (paths.personal_root / "secrets.csv").write_bytes(b"personal fixture")
    make_directory_link(paths.market_root / "daily_price", paths.personal_root)
    assert_code("linked_path", lambda: plan_market_only_export(paths, ["daily_price/secrets.csv"], destination_root=destination))


def test_hardlink_to_personal_rejected(layout):
    paths, destination = layout
    paths.personal_root.mkdir()
    secret = paths.personal_root / "secret.csv"
    secret.write_bytes(b"private fixture")
    source = paths.market_root / "daily_price" / "secret.csv"
    source.parent.mkdir()
    os.link(secret, source)
    assert_code("hardlinked_export_file", lambda: plan_market_only_export(paths, ["daily_price/secret.csv"], destination_root=destination))


def test_file_change_invalidates_plan(layout):
    paths, destination = layout
    source = create_market_file(paths)
    plan = plan_market_only_export(paths, ["daily_price/20261002.csv"], destination_root=destination)
    source.write_bytes(b"changed fixture")
    assert_code("export_file_changed", plan.validate)


def test_junction_swap_invalidates_existing_plan(layout):
    paths, destination = layout
    source = create_market_file(paths)
    plan = plan_market_only_export(paths, ["daily_price/20261002.csv"], destination_root=destination)
    source.parent.rename(paths.market_root / "old_daily")
    make_directory_link(paths.market_root / "daily_price", paths.market_root / "old_daily")
    assert_code("linked_path", plan.validate)


def test_duplicate_files_rejected(layout):
    paths, destination = layout
    create_market_file(paths)
    assert_code("duplicate_export_file", lambda: plan_market_only_export(
        paths, ["daily_price/20261002.csv"] * 2, destination_root=destination,
    ))


def test_directory_and_missing_sources_rejected(layout):
    paths, destination = layout
    folder = paths.market_root / "daily_price" / "folder.csv"
    folder.mkdir(parents=True)
    assert_code("export_regular_file_required", lambda: plan_market_only_export(paths, ["daily_price/folder.csv"], destination_root=destination))
    assert_code("export_file_unavailable", lambda: plan_market_only_export(paths, ["daily_price/missing.csv"], destination_root=destination))


def test_legacy_json_preserved_and_excluded(layout):
    paths, destination = layout
    legacy = paths.legacy_output_root / "watchlist" / "default.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'{ "version": 1, "items": [] }\n')
    before = legacy.read_bytes()
    create_market_file(paths)
    plan_market_only_export(paths, ["daily_price/20261002.csv"], destination_root=destination)
    assert legacy.read_bytes() == before
    assert not paths.watchlist_db.exists()


def test_custom_output_in_market_whitelist_is_still_excluded(tmp_path):
    paths = resolve_personal_data_paths(tmp_path / "market", personal_root=tmp_path / "personal",
                                       legacy_output_root=tmp_path / "market" / "daily_price")
    create_market_file(paths)
    assert_code("legacy_output_excluded", lambda: plan_market_only_export(
        paths, ["daily_price/20261002.csv"], destination_root=tmp_path / "package",
    ))

def test_personal_database_hardlink_rejected(layout):
    paths, _ = layout
    market_file = create_market_file(paths)
    paths.watchlist_db.parent.mkdir(parents=True)
    os.link(market_file, paths.watchlist_db)
    assert_code("hardlinked_personal_file", paths.validate)


@pytest.mark.parametrize("which", ["market", "personal", "output"])
def test_regular_file_cannot_be_root(tmp_path, which):
    roots = {name: tmp_path / name for name in ("market", "personal", "output")}
    roots[which].write_bytes(b"fixture")
    assert_code("directory_root_required", lambda: resolve_personal_data_paths(
        roots["market"], personal_root=roots["personal"], legacy_output_root=roots["output"],
    ))


def test_export_destination_file_rejected(layout):
    paths, destination = layout
    create_market_file(paths)
    destination.write_bytes(b"fixture")
    assert_code("directory_root_required", lambda: plan_market_only_export(
        paths, ["daily_price/20261002.csv"], destination_root=destination,
    ))


def test_export_destination_child_junction_rejected(layout):
    paths, destination = layout
    create_market_file(paths)
    destination.mkdir()
    make_directory_link(destination / "daily_price", paths.market_root)
    assert_code("linked_path", lambda: plan_market_only_export(
        paths, ["daily_price/20261002.csv"], destination_root=destination,
    ))


@pytest.mark.skipif(os.name != "nt", reason="Windows 路徑規則")
@pytest.mark.parametrize("name", ["daily_price/test.csv.", "daily_price/CON.csv", "daily_price/alias /other.csv"])
def test_windows_path_aliases_fail_closed(layout, name):
    paths, destination = layout
    expected = "market_export_not_allowlisted" if name.endswith(".") else "ambiguous_windows_path" if "CON" in name or "alias " in name else "export_file_unavailable"
    assert_code(expected, lambda: plan_market_only_export(paths, [name], destination_root=destination))

@pytest.mark.skipif(os.name != "nt", reason="Windows 裝置路徑規則")
@pytest.mark.parametrize("prefix", ["\\\\?\\", "\\\\.\\"])
def test_windows_device_namespace_root_rejected(tmp_path, prefix):
    assert_code("ambiguous_windows_path", lambda: resolve_personal_data_paths(
        tmp_path / "market", personal_root=prefix + str(tmp_path / "personal"),
    ))

def internal_layout(tmp_path):
    market = tmp_path / "FA_Data"
    return resolve_personal_data_paths(market, personal_root=market / "personal", environ={})


def test_exact_personal_subtree_resolves_without_creating_directories(tmp_path):
    paths = internal_layout(tmp_path)
    assert paths.personal_root == paths.market_root / "personal"
    for path in (paths.watchlist_db, paths.activation_marker, paths.conversion_receipt,
                 paths.backup_root, paths.marker_backup_root, paths.research_notes_root, paths.ledger_root):
        assert path.is_relative_to(paths.personal_root)
        assert path != paths.market_root / "sqlite/twstock.db"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("child", ["", "sqlite", "sqlite/personal", "daily_price", "daily_price/personal",
                                  "output", "output/personal", "technical_analysis", "personal/notes", "personalized"])
def test_only_exact_market_personal_subtree_is_allowed(tmp_path, child):
    market = tmp_path / "FA_Data"
    assert_code("overlapping_roots", lambda: resolve_personal_data_paths(
        market, personal_root=market / child, environ={},
    ))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("child", ["personal", "personal/cache", ""])
def test_legacy_output_may_not_overlap_internal_personal(tmp_path, child):
    market = tmp_path / "FA_Data"
    assert_code("overlapping_roots", lambda: resolve_personal_data_paths(
        market, personal_root=market / "personal", legacy_output_root=market / child, environ={},
    ))


@pytest.mark.parametrize("name", ["personal/watchlists/watchlists.v3.sqlite", "personal/research_notes/journal_entries.jsonl",
                                 "personal/notes.csv", "Personal/notes.csv", "personal/backups/research_notes/a.csv"])
def test_market_export_rejects_personal_subtree_even_csv(tmp_path, name):
    paths = internal_layout(tmp_path)
    assert_code("personal_subtree_excluded", lambda: plan_market_only_export(
        paths, [name], destination_root=tmp_path / "package",
    ))
    assert not paths.market_root.exists()


def test_scan_of_market_tree_with_personal_file_is_rejected(tmp_path):
    paths = internal_layout(tmp_path)
    create_market_file(paths)
    secret = paths.personal_root / "notes.csv"
    secret.parent.mkdir()
    secret.write_bytes(b"synthetic private")
    names = [p.relative_to(paths.market_root).as_posix() for p in paths.market_root.rglob("*.csv")]
    assert_code("personal_subtree_excluded", lambda: plan_market_only_export(
        paths, names, destination_root=tmp_path / "package",
    ))
    selected = plan_market_only_export(paths, ["daily_price/20261002.csv"], destination_root=tmp_path / "package")
    selected.validate()
    assert [f.relative_path for f in selected.files] == ["daily_price/20261002.csv"]
    assert secret.read_bytes() == b"synthetic private"
    assert not (tmp_path / "package").exists()


def test_internal_personal_hardlink_into_csv_whitelist_rejected(tmp_path):
    paths = internal_layout(tmp_path)
    secret = paths.research_notes_root / "fixture.csv"
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"synthetic private")
    allowed = paths.market_root / "daily_price/private.csv"
    allowed.parent.mkdir()
    os.link(secret, allowed)
    assert_code("hardlinked_export_file", lambda: plan_market_only_export(
        paths, ["daily_price/private.csv"], destination_root=tmp_path / "package",
    ))


@pytest.mark.parametrize("child", ["personal", "personal/watchlists", "daily_price"])
def test_internal_root_or_market_cross_junction_rejected(tmp_path, child):
    paths = internal_layout(tmp_path)
    outside = tmp_path / "outside"; outside.mkdir()
    link = paths.market_root / child
    link.parent.mkdir(parents=True, exist_ok=True)
    target = paths.personal_root if child == "daily_price" else outside
    target.mkdir(parents=True, exist_ok=True)
    try:
        make_directory_link(link, target)
        if child == "daily_price":
            assert_code("linked_path", lambda: plan_market_only_export(
                paths, ["daily_price/secret.csv"], destination_root=tmp_path / "package",
            ))
        else:
            assert_code("linked_path", paths.validate)
    finally:
        if os.path.lexists(link):
            if os.name == "nt": os.rmdir(link)
            else: link.unlink()


def test_internal_cow_controls_and_legacy_source_boundary(tmp_path):
    from app_module.personal_data_paths import WatchlistCowControlPaths
    paths = internal_layout(tmp_path)
    source = paths.legacy_output_root / "watchlist/default.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"version":1,"items":[]}\n')
    before = source.read_bytes()
    controls = WatchlistCowControlPaths(paths, source)
    controls.validate(source, paths.watchlist_db)
    for path in (controls.marker_path, controls.lock_path, controls.receipt_path, controls.source_backup_path,
                 controls.backup_marker_path("a"*32)):
        assert path.is_relative_to(paths.personal_root)
    assert source.read_bytes() == before
    assert not paths.personal_root.exists()
    fake_source = paths.personal_root / "old.json"
    assert_code("source_in_personal_subtree", lambda: WatchlistCowControlPaths(paths, fake_source).validate(
        fake_source, paths.watchlist_db,
    ))


@pytest.mark.parametrize("kind", ["json", "1", "2"])
def test_cow_synthetic_pipeline_with_new_internal_root(tmp_path, kind):
    _cow_synthetic_pipeline(tmp_path, kind)


@pytest.mark.parametrize("kind", ["json", "1", "2"])
@pytest.mark.parametrize("levels", [4, 7], ids=["long_control_suffix", "long_canonical_db"])
def test_cow_synthetic_pipeline_deep_unicode_new_process(tmp_path, kind, levels):
    root = tmp_path.joinpath(*(["合法深層資料夾" * 3] * levels))
    if os.name == "nt" and levels == 7:
        assert len(str(internal_layout(root).watchlist_db)) > 260
    _cow_synthetic_pipeline(root, kind, new_process=True)


def _cow_synthetic_pipeline(tmp_path, kind, *, new_process=False):
    import json
    from app_module.personal_data_paths import WatchlistCowControlPaths
    from app_module.watchlist_cow_activation import activate_watchlist_sqlite, rollback_watchlist_sqlite, PersonalWatchlistCowService
    from data_module.watchlist_json_cow import convert_watchlist_json
    from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite, _io_path, _stat_record
    from test_watchlist_cow_activation import _build_source
    paths = internal_layout(tmp_path)
    source = paths.legacy_output_root / "watchlist" / ("default.json" if kind == "json" else "watchlists.db")
    _io_path(source.parent).mkdir(parents=True)
    if kind == "json":
        _io_path(source).write_text(json.dumps({"version": 1, "name": "fixture", "items": [{
            "stock_code": "2330", "stock_name": "fixture", "added_at": "2026-10-01T09:00:00",
            "source": "manual", "notes": "synthetic", "tags": [],
        }], "created_at": "2026-10-01T09:00:00", "updated_at": "2026-10-01T09:00:00"}), encoding="utf-8")
    else:
        _build_source(_io_path(source), int(kind))
    before = _io_path(source).read_bytes(), _io_path(source).stat().st_mtime_ns
    source_pin = _stat_record(source)
    controls = WatchlistCowControlPaths(paths, source)
    converter = convert_watchlist_json if kind == "json" else convert_watchlist_sqlite
    result = converter(source, paths.watchlist_db, control_paths=controls)
    assert result["status"] == "ready", result
    assert result["source_path"] == str(source)
    assert result["source_stat"] == source_pin
    assert result["source_sha256"] == hashlib.sha256(before[0]).hexdigest()
    receipt_bytes = _io_path(controls.receipt_path).read_bytes()
    assert result["target_path"] == str(paths.watchlist_db)
    if new_process and os.name == "nt":
        assert len(str(controls.source_backup_path)) > 260
        assert len(str(paths.watchlist_db)) > 200
    assert activate_watchlist_sqlite(source, paths.watchlist_db, control_paths=controls)["status"] == "activated"
    service = PersonalWatchlistCowService(controls)
    loaded = service.load("default")
    assert loaded is not None
    payload, revision = loaded
    payload["items"].append({"stock_code": "9999", "stock_name": "synthetic", "source": "manual",
                             "added_at": "2026-10-01T09:00:00", "tags": [], "notes": "fixture"})
    assert service.save("default", payload, expected_revision=revision) == revision + 1
    target_bytes = _io_path(paths.watchlist_db).read_bytes()
    assert hashlib.sha256(target_bytes).hexdigest() != result["target_sha256"]
    if new_process:
        _assert_cow_new_process(paths.market_root, source, revision + 1, "active", before)
    assert rollback_watchlist_sqlite(source, control_paths=controls)["status"] == "rolled_back"
    assert _io_path(paths.watchlist_db).read_bytes() == target_bytes
    assert (_io_path(source).read_bytes(), _io_path(source).stat().st_mtime_ns) == before
    assert _stat_record(source) == source_pin
    assert _io_path(controls.receipt_path).read_bytes() == receipt_bytes
    assert not _io_path(source.with_name(source.name+".cow-active.json")).exists()
    assert not _io_path(paths.market_root.joinpath("sqlite/twstock.db")).exists()
    assert _io_path(controls.marker_path).exists() and _io_path(controls.receipt_path).exists()
    if new_process:
        _assert_cow_new_process(paths.market_root, source, revision + 1, "rolled_back", before)


def _assert_cow_new_process(market_root, source, revision, status, before):
    script = """
import hashlib, sys
from pathlib import Path
from app_module.personal_data_paths import resolve_personal_data_paths, WatchlistCowControlPaths
from app_module.watchlist_cow_activation import resolve_watchlist_sqlite_activation, PersonalWatchlistCowService
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_sqlite_cow import _io_path
market, source = Path(sys.argv[1]), Path(sys.argv[2])
paths = resolve_personal_data_paths(market, personal_root=market / 'personal', environ={})
controls = WatchlistCowControlPaths(paths, source)
assert resolve_watchlist_sqlite_activation(source, control_paths=controls)['status'] == sys.argv[4]
loaded = WatchlistRepository(paths.watchlist_db).load('default')
assert loaded is not None and loaded[1] == int(sys.argv[3])
assert loaded[0]['items'][-1]['stock_code'] == '9999'
if sys.argv[4] == 'active':
    assert PersonalWatchlistCowService(controls).load('default') == loaded
assert hashlib.sha256(_io_path(source).read_bytes()).hexdigest() == sys.argv[5]
assert _io_path(source).stat().st_mtime_ns == int(sys.argv[6])
"""
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-c", script, str(market_root), str(source),
         str(revision), status, hashlib.sha256(before[0]).hexdigest(), str(before[1])],
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows 深路徑 I/O 防禦")
@pytest.mark.parametrize("which", ["source_backup", "rollback", "receipt_stage"])
def test_deep_unicode_control_hardlinks_rejected(tmp_path, which):
    from app_module.personal_data_paths import WatchlistCowControlPaths
    from data_module.watchlist_sqlite_cow import _io_path
    root = tmp_path.joinpath(*(["合法深層資料夾" * 3] * 4))
    paths = internal_layout(root)
    source = paths.legacy_output_root / "watchlist/default.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic source")
    controls = WatchlistCowControlPaths(paths, source)
    controls.prepare_directories()
    target = {"source_backup": controls.source_backup_path,
              "rollback": controls.backup_marker_path("a" * 32),
              "receipt_stage": controls.receipt_path.with_name(
                  controls.receipt_path.name + ".stage-" + "a" * 32)}[which]
    assert len(str(target)) > 260
    os.link(_io_path(source), _io_path(target))
    with pytest.raises(PersonalDataPathError, match="hardlinked"):
        controls.assert_personal(target)
    assert source.read_bytes() == b"synthetic source"


@pytest.mark.skipif(os.name != "nt", reason="Windows 深路徑 reparse 防禦")
def test_deep_unicode_control_directory_junction_rejected(tmp_path):
    from app_module.personal_data_paths import WatchlistCowControlPaths
    from data_module.watchlist_sqlite_cow import _io_path
    root = tmp_path.joinpath(*(["合法深層資料夾" * 3] * 4))
    paths = internal_layout(root)
    source = paths.legacy_output_root / "watchlist/default.json"
    _io_path(source.parent).mkdir(parents=True)
    _io_path(source).write_bytes(b"synthetic source")
    controls = WatchlistCowControlPaths(paths, source)
    controls.prepare_directories()
    outside = tmp_path / "synthetic_outside"
    outside.mkdir()
    link = paths.personal_root / ("linked_directory_" + "x" * 70)
    assert len(str(link)) > 260
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(_io_path(link)), str(outside)],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    with pytest.raises(PersonalDataPathError, match="linked_path"):
        controls.assert_personal(link / "guard.json")
    assert list(outside.iterdir()) == []
    assert _io_path(source).read_bytes() == b"synthetic source"


@pytest.mark.parametrize("which", ["db", "marker", "receipt", "lock", "source_backup", "rollback"])
def test_internal_control_artifact_hardlinks_rejected(tmp_path, which):
    from app_module.personal_data_paths import WatchlistCowControlPaths
    paths = internal_layout(tmp_path)
    source = paths.legacy_output_root / "watchlist/default.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic source")
    controls = WatchlistCowControlPaths(paths, source)
    target = {"db": paths.watchlist_db, "marker": controls.marker_path, "receipt": controls.receipt_path,
              "lock": controls.lock_path, "source_backup": controls.source_backup_path,
              "rollback": controls.backup_marker_path("a"*32)}[which]
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)
    with pytest.raises(PersonalDataPathError, match="hardlinked"):
        controls.assert_personal(target)
    assert source.read_bytes() == b"synthetic source"


def test_internal_root_alias_and_escape_forms_rejected(tmp_path):
    market = tmp_path / "FA_Data"
    assert_code("absolute_path_required", lambda: resolve_personal_data_paths(
        market, personal_root=market / "personal" / ".." / "personal", environ={},
    ))
    if os.name == "nt":
        for spelling in ("personal.", "personal ", "personal:notes", "CON"):
            assert_code("ambiguous_windows_path", lambda spelling=spelling: resolve_personal_data_paths(
                market, personal_root=market / spelling, environ={},
            ))
    assert not market.exists()


def test_internal_root_environment_is_explicit_and_external_still_opt_in(tmp_path):
    market = tmp_path / "FA_Data"
    paths = resolve_personal_data_paths(market, environ={"PERSONAL_DATA_ROOT": str(market / "personal")})
    assert paths.personal_root == market / "personal"
    assert_code("personal_root_unconfigured", lambda: resolve_personal_data_paths(market, environ={}))
    external = resolve_personal_data_paths(market, personal_root=tmp_path / "custom", environ={})
    assert external.personal_root == tmp_path / "custom"
    assert not market.exists() and not external.personal_root.exists()
