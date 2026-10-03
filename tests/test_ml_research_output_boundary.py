from __future__ import annotations

from pathlib import Path

import pytest

from data_module.ml_research_output_boundary import (
    MLResearchOutputBoundaryError,
    resolve_ml_research_output_path,
)


def _research_root(repository_root: Path) -> Path:
    root = repository_root / "output" / "ml_research"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_resolver_accepts_only_repository_research_root(
    tmp_path: Path,
) -> None:
    root = _research_root(tmp_path)
    requested = root / "run" / "manifest.json"

    assert resolve_ml_research_output_path(
        requested,
        repository_root=tmp_path,
    ) == requested.resolve()
    assert resolve_ml_research_output_path(
        Path("output") / "ml_research" / "run" / "manifest.json",
        repository_root=tmp_path,
    ) == requested.resolve()


@pytest.mark.parametrize(
    "relative_path",
    (
        Path("output") / "ml_research_copy" / "candidate",
        Path("output") / "release_v4" / "candidate",
        Path("output") / "v4_ml_derived_h5_20260907_real_v2" / "manifest.json",
        Path("..") / "output" / "ml_research" / "escaped",
    ),
)
def test_resolver_rejects_prefix_escape_and_formal_roots(
    tmp_path: Path,
    relative_path: Path,
) -> None:
    _research_root(tmp_path)

    with pytest.raises(MLResearchOutputBoundaryError):
        resolve_ml_research_output_path(relative_path, repository_root=tmp_path)


def test_resolver_rejects_configured_data_root_even_under_research_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = _research_root(tmp_path) / "source-data"
    protected.mkdir()
    monkeypatch.setenv("DATA_ROOT", str(protected))

    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        resolve_ml_research_output_path(
            protected / "candidate",
            repository_root=tmp_path,
        )


def test_resolver_rejects_extra_formal_registry_root(
    tmp_path: Path,
) -> None:
    root = _research_root(tmp_path)
    registry = root / "formal-registry"

    with pytest.raises(MLResearchOutputBoundaryError, match="protected root"):
        resolve_ml_research_output_path(
            registry / "latest.json",
            repository_root=tmp_path,
            extra_forbidden_roots=(registry,),
        )


def test_resolver_rejects_symlink_alias_inside_approved_root(
    tmp_path: Path,
) -> None:
    root = _research_root(tmp_path)
    target = root / "target"
    target.mkdir()
    alias = root / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"作業系統未授予建立測試 symlink 的權限：{exc}")

    with pytest.raises(MLResearchOutputBoundaryError, match="symlink or junction"):
        resolve_ml_research_output_path(
            alias / "candidate",
            repository_root=tmp_path,
        )
