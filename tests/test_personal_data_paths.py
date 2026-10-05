"""全部使用 synthetic fixtures；不讀取正式 JSON／市場 DB。"""

import os
import subprocess
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