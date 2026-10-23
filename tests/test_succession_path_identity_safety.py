from pathlib import Path

from data_module.repository_output_path_identity import same_output_scope, same_repository_output_path
from data_module.scheduled_research_acquisition_binding import _path_matches_relocated
from scripts.scheduled.paper_portfolio_state_isolation import _same_or_relocated_source_path
from scripts.scheduled.run_paper_execution_daily_isolated import _scope_value_matches_relocated
from scripts.scheduled.run_formal_pit_sidecar_postcutoff import _find_taxonomy_bundle, PIT_TAXONOMY_PREOPEN_ROOT_ENV
from datetime import date
import pytest


def test_nonexistent_drive_relocation_is_not_identity(tmp_path):
    old = r"D:\Min\Python\Project\FA_Data\output\paper_portfolio\paper_portfolio.sqlite"
    new = Path(r"F:\Min\Python\Project\FA_Data\output\paper_portfolio\paper_portfolio.sqlite")
    assert not _same_or_relocated_source_path(old, new)
    assert not _path_matches_relocated(old, new)
    assert not same_repository_output_path(old, new, repository_root=tmp_path)


def test_scope_does_not_rewrite_strategy_or_missing_source():
    old = {"strategy": r"D:\Min\Python\Project\FA_Data\strategy"}
    new = {"strategy": r"F:\Min\Python\Project\FA_Data\strategy"}
    assert not _scope_value_matches_relocated(old, new)
    assert not _scope_value_matches_relocated({"path": old["strategy"]}, {"path": new["strategy"]})


def test_exact_scope_preserves_nonpath_contract(tmp_path):
    body = {"strategy": "paper-main", "source": {"state_db": str(tmp_path / "db")}, "cash": "0"}
    assert same_output_scope(body, body, repository_root=tmp_path)
    assert not same_output_scope(body, {**body, "cash": "500000"}, repository_root=tmp_path)


def test_different_output_files_and_relative_paths_rejected(tmp_path):
    root = tmp_path / "repo"
    output = root / "output"
    output.mkdir(parents=True)
    a, b = output / "a.json", output / "b.json"
    a.write_text("same")
    b.write_text("same")
    assert not same_repository_output_path(str(a), b, repository_root=root)
    assert not same_repository_output_path("output/a.json", a, repository_root=root)
    assert same_repository_output_path(str(a), a, repository_root=root)


def test_taxonomy_multiple_sources_require_explicit_selection(tmp_path, monkeypatch):
    monkeypatch.delenv(PIT_TAXONOMY_PREOPEN_ROOT_ENV, raising=False)
    for name in ("pit_taxonomy_preopen", "pit_taxonomy_preopen_split_v2"):
        folder = tmp_path / name / "2026-10-22"
        folder.mkdir(parents=True)
        (folder / "bundle_manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="ambiguous"):
        _find_taxonomy_bundle(tmp_path, target_date=date(2026, 10, 22))
    selected = tmp_path / "pit_taxonomy_preopen_split_v2"
    monkeypatch.setenv(PIT_TAXONOMY_PREOPEN_ROOT_ENV, str(selected))
    assert _find_taxonomy_bundle(tmp_path, target_date=date(2026, 10, 22)) == selected / "2026-10-22/bundle_manifest.json"


def test_existing_repository_output_mount_alias_is_same_physical_directory():
    root = Path(__file__).resolve().parents[1]
    mount = root / "output"
    if not mount.is_dir():
        pytest.skip("repository output mount absent")
    assert same_repository_output_path(str(mount), mount.resolve(strict=True), repository_root=root)
    if mount != mount.resolve():
        assert not same_output_scope(
            {"strategy": str(mount)}, {"strategy": str(mount.resolve())}, repository_root=root,
        )
