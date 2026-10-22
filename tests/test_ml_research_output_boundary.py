from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from data_module.config import TWStockConfig
from data_module.ml_research_output_boundary import (
    ML_RESEARCH_STORAGE_CONFIG_ENV,
    ML_RESEARCH_STORAGE_SCHEMA_VERSION,
    MLResearchOutputBoundaryError,
    get_ml_research_root,
    resolve_ml_research_output_path,
)


@pytest.fixture(autouse=True)
def _clear_storage_config_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ML_RESEARCH_STORAGE_CONFIG_ENV, raising=False)


def _write_config(repository: Path, active_root: str | Path, *, body: bytes | None = None) -> Path:
    config_path = repository / "output" / "ml_research_storage.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = json.dumps(
            {
                "schema_version": ML_RESEARCH_STORAGE_SCHEMA_VERSION,
                "active_root": str(active_root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    config_path.write_bytes(body)
    return config_path


def _write_config_path(
    config_path: Path, active_root: str | Path, *, body: bytes | None = None
) -> Path:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = json.dumps(
            {
                "schema_version": ML_RESEARCH_STORAGE_SCHEMA_VERSION,
                "active_root": str(active_root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    config_path.write_bytes(body)
    return config_path


def _make_true_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("true mount-point junctions require Windows")
    link.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return
    output = f"{completed.stdout}\n{completed.stderr}".casefold()
    if any(marker in output for marker in ("access is denied", "privilege", "requires elevation")):
        pytest.skip(f"junction creation unavailable: {output.strip()}")
    pytest.fail(f"junction creation failed: {output.strip()}")


def test_absent_config_keeps_legacy_root_active_without_creating_it(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    legacy = repository / "output" / "ml_research"

    assert get_ml_research_root(repository_root=repository) == legacy
    assert not legacy.exists()
    assert resolve_ml_research_output_path(
        legacy / "runs" / "old" / "manifest.json",
        repository_root=repository,
        access="read",
    ) == legacy / "runs" / "old" / "manifest.json"
    assert resolve_ml_research_output_path(
        legacy / "new" / "manifest.json",
        repository_root=repository,
        access="write",
    ) == legacy / "new" / "manifest.json"
    assert not legacy.exists()


def test_legacy_ml_root_accepts_only_the_repository_output_junction(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    storage = tmp_path / "owner-configured-storage"
    _make_true_junction(repository / "output", storage)
    legacy = storage / "ml_research"

    assert get_ml_research_root(repository_root=repository) == legacy
    assert resolve_ml_research_output_path(
        repository / "output" / "ml_research" / "runs" / "old.json",
        repository_root=repository,
        access="read",
    ) == legacy / "runs" / "old.json"
    assert resolve_ml_research_output_path(
        repository / "output" / "ml_research" / "runs" / "new.json",
        repository_root=repository,
        access="write",
    ) == legacy / "runs" / "new.json"


def test_storage_config_under_repository_output_junction_keeps_active_root_separate(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    storage = tmp_path / "owner-configured-storage"
    _make_true_junction(repository / "output", storage)
    active = tmp_path / "independent-ml-research"
    _write_config(repository, active)

    assert get_ml_research_root(repository_root=repository) == active
    assert resolve_ml_research_output_path(
        repository / "output" / "ml_research" / "old" / "manifest.json",
        repository_root=repository,
        access="read",
    ) == storage / "ml_research" / "old" / "manifest.json"
    assert resolve_ml_research_output_path(
        active / "new" / "manifest.json",
        repository_root=repository,
        access="write",
    ) == active / "new" / "manifest.json"


def test_ml_candidate_cannot_use_a_reparse_point_at_another_repository_location(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    (repository / "output").mkdir(parents=True)
    outside = tmp_path / "other-storage"
    _make_true_junction(repository / "other", outside)

    with pytest.raises(MLResearchOutputBoundaryError, match="symlink or junction"):
        resolve_ml_research_output_path(
            repository / "other" / "manifest.json",
            repository_root=repository,
            access="read",
        )


def test_legacy_ml_root_junction_cannot_overlap_formal_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    formal_data = tmp_path / "formal-data"
    _make_true_junction(repository / "output", formal_data)
    monkeypatch.setenv("DATA_ROOT", str(formal_data))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "formal-output"))

    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        get_ml_research_root(repository_root=repository)


def test_configured_root_is_only_write_root_while_legacy_pins_remain_readable(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    legacy = repository / "output" / "ml_research"
    active = tmp_path / "D" / "FA_ML_Research"
    _write_config(repository, active)

    assert get_ml_research_root(repository_root=repository) == active
    assert not active.exists()
    assert resolve_ml_research_output_path(
        legacy / "old-cycle" / "terminal.json",
        repository_root=repository,
        access="read",
    ) == legacy / "old-cycle" / "terminal.json"
    assert resolve_ml_research_output_path(
        active / "new-cycle" / "terminal.json",
        repository_root=repository,
        access="read",
    ) == active / "new-cycle" / "terminal.json"
    assert resolve_ml_research_output_path(
        active / "new-cycle" / "terminal.json",
        repository_root=repository,
        access="write",
    ) == active / "new-cycle" / "terminal.json"
    with pytest.raises(MLResearchOutputBoundaryError, match="writes must be"):
        resolve_ml_research_output_path(
            legacy / "new-cycle" / "terminal.json",
            repository_root=repository,
            access="write",
        )
    with pytest.raises(MLResearchOutputBoundaryError, match="inside the legacy or configured"):
        resolve_ml_research_output_path(
            tmp_path / "unapproved" / "manifest.json",
            repository_root=repository,
            access="read",
        )


def test_explicit_external_config_supports_frozen_repository_without_creating_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "frozen" / "_internal"
    repository.mkdir(parents=True)
    legacy = repository / "output" / "ml_research"
    external_config = tmp_path / "user-config" / "ml_research_storage.json"
    active = tmp_path / "user-data" / "FA_ML_Research"
    _write_config_path(external_config, active)
    monkeypatch.setenv(ML_RESEARCH_STORAGE_CONFIG_ENV, str(external_config))

    assert get_ml_research_root(repository_root=repository) == active
    assert resolve_ml_research_output_path(
        legacy / "old" / "terminal.json",
        repository_root=repository,
        access="read",
    ) == legacy / "old" / "terminal.json"
    assert resolve_ml_research_output_path(
        active / "current" / "terminal.json",
        repository_root=repository,
        access="read",
    ) == active / "current" / "terminal.json"
    assert resolve_ml_research_output_path(
        active / "current" / "terminal.json",
        repository_root=repository,
        access="write",
    ) == active / "current" / "terminal.json"
    with pytest.raises(MLResearchOutputBoundaryError, match="writes must be"):
        resolve_ml_research_output_path(
            legacy / "new" / "terminal.json",
            repository_root=repository,
            access="write",
        )
    assert not active.exists()
    assert not legacy.exists()


@pytest.mark.parametrize("configured_path", ["", "   ", "relative/config.json"])
def test_explicit_empty_or_relative_config_path_fails_without_default_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_path: str,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    default_active = tmp_path / "default-active"
    _write_config(repository, default_active)
    monkeypatch.setenv(ML_RESEARCH_STORAGE_CONFIG_ENV, configured_path)

    with pytest.raises(MLResearchOutputBoundaryError, match="absolute path"):
        get_ml_research_root(repository_root=repository)
    assert not default_active.exists()


def test_explicit_missing_or_invalid_external_config_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    default_active = tmp_path / "default-active"
    _write_config(repository, default_active)
    missing_config = tmp_path / "external" / "missing.json"
    monkeypatch.setenv(ML_RESEARCH_STORAGE_CONFIG_ENV, str(missing_config))

    with pytest.raises(MLResearchOutputBoundaryError, match="does not exist"):
        get_ml_research_root(repository_root=repository)
    assert not default_active.exists()

    external_config = _write_config_path(
        tmp_path / "external" / "invalid.json",
        tmp_path / "safe-active",
        body=b'{"schema_version":"wrong","active_root":"D:/ML"}',
    )
    monkeypatch.setenv(ML_RESEARCH_STORAGE_CONFIG_ENV, str(external_config))
    with pytest.raises(MLResearchOutputBoundaryError, match="schema version"):
        get_ml_research_root(repository_root=repository)
    assert not default_active.exists()
    assert not (tmp_path / "safe-active").exists()


def test_current_observed_reader_resolves_exact_legacy_and_active_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ml_module.recommendation_calibration_evidence as evidence_module

    repository = tmp_path / "repo"
    repository.mkdir()
    legacy = repository / "output" / "ml_research"
    active = tmp_path / "D" / "FA_ML_Research"
    _write_config(repository, active)
    monkeypatch.setattr(
        evidence_module, "_CURRENT_OBSERVED_RESEARCH_ROOT", legacy
    )

    roots = evidence_module._current_observed_research_roots()

    assert roots == (legacy.resolve(strict=False), active.resolve(strict=False))
    cycle_receipt = active / "current_stock_cycles" / "2026-10-05" / "cycle-key" / "terminal.json"
    assert evidence_module._is_below_current_observed_cycle_root(cycle_receipt, roots)
    assert not evidence_module._is_below_current_observed_cycle_root(
        tmp_path / "other" / "terminal.json", roots
    )


@pytest.mark.parametrize(
    "active_root",
    ["relative/research"],
)
def test_config_rejects_relative_or_protected_active_roots(
    tmp_path: Path, active_root: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _write_config(repository, active_root)

    with pytest.raises(MLResearchOutputBoundaryError):
        get_ml_research_root(repository_root=repository)


def test_config_rejects_active_root_inside_configured_formal_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    formal_data = tmp_path / "isolated-formal-data"
    _write_config(repository, formal_data / "output" / "research")
    monkeypatch.setenv("DATA_ROOT", str(formal_data))
    monkeypatch.setenv("OUTPUT_ROOT", str(formal_data / "output"))

    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        get_ml_research_root(repository_root=repository)


def test_config_rejects_known_shadow_roots_but_not_a_name_substring(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    data_root_factory = TWStockConfig.__dataclass_fields__["data_root"].default_factory
    data_root = Path(data_root_factory())
    _write_config(
        repository,
        data_root.parent / "FA_Data_Shadow" / "research",
    )
    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        get_ml_research_root(repository_root=repository)

    legal_root = tmp_path / "test_shadow_root" / "FA_ML_Research"
    _write_config(repository, legal_root)
    assert get_ml_research_root(repository_root=repository) == legal_root


def test_repo_output_root_override_does_not_block_legacy_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "FA_Data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(repository / "output"))

    legacy = repository / "output" / "ml_research"
    assert get_ml_research_root(repository_root=repository) == legacy
    assert resolve_ml_research_output_path(
        legacy / "old" / "manifest.json",
        repository_root=repository,
        access="read",
    ) == legacy / "old" / "manifest.json"


def test_config_rejects_overlap_with_legacy_root_and_parent_traversal(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    legacy = repository / "output" / "ml_research"
    _write_config(repository, legacy / "new")
    with pytest.raises(MLResearchOutputBoundaryError, match="separate from the legacy"):
        get_ml_research_root(repository_root=repository)

    _write_config(repository, str(tmp_path / "safe" / ".." / "escape"))
    with pytest.raises(MLResearchOutputBoundaryError, match="cannot contain"):
        get_ml_research_root(repository_root=repository)


@pytest.mark.parametrize(
    "payload",
    [
        b"{not-json",
        b'{"schema_version":"wrong","active_root":"D:/ML"}',
        b'{"schema_version":"ml-research-storage.v1","active_root":"D:/A","active_root":"D:/B"}',
        b'{"schema_version":"ml-research-storage.v1","active_root":"D:/ML","extra":true}',
    ],
)
def test_existing_invalid_config_fails_closed_instead_of_using_legacy(
    tmp_path: Path, payload: bytes
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _write_config(repository, "D:/ML", body=payload)

    with pytest.raises(MLResearchOutputBoundaryError):
        get_ml_research_root(repository_root=repository)
    with pytest.raises(MLResearchOutputBoundaryError):
        resolve_ml_research_output_path(
            repository / "output" / "ml_research" / "old.json",
            repository_root=repository,
            access="read",
        )


def test_config_is_bounded_and_storage_file_reparse_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    config_path = _write_config(repository, "D:/ML")
    config_path.write_bytes(b" " * (16 * 1024 + 1))
    with pytest.raises(MLResearchOutputBoundaryError, match="bounded size"):
        get_ml_research_root(repository_root=repository)

    target = tmp_path / "config-target.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": ML_RESEARCH_STORAGE_SCHEMA_VERSION,
                "active_root": "D:/ML",
            }
        ),
        encoding="utf-8",
    )
    try:
        config_path.unlink()
        config_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("This Windows environment cannot create a symlink for the negative test")
    with pytest.raises(MLResearchOutputBoundaryError, match="reparse"):
        get_ml_research_root(repository_root=repository)


def test_extra_forbidden_root_and_candidate_reparse_are_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    active = tmp_path / "D" / "FA_ML_Research"
    _write_config(repository, active)
    protected = active / "protected"
    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        resolve_ml_research_output_path(
            protected / "manifest.json",
            repository_root=repository,
            extra_forbidden_roots=(protected,),
            access="write",
        )

    target = tmp_path / "external"
    target.mkdir()
    link = active / "alias"
    active.mkdir(parents=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("This Windows environment cannot create a symlink for the negative test")
    with pytest.raises(MLResearchOutputBoundaryError, match="symlink or junction"):
        resolve_ml_research_output_path(
            link / "escape.json",
            repository_root=repository,
            access="write",
        )
