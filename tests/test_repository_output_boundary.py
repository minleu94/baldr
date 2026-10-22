from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from runtime.repository_output import (
    RepositoryOutputBoundaryError,
    resolve_repository_output_path,
    resolve_repository_output_root,
)


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


def test_regular_repository_output_directory_remains_supported(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    output = repository / "output"
    output.mkdir(parents=True)

    assert resolve_repository_output_root(repository) == output.resolve()
    assert resolve_repository_output_path(
        output / "ml_research" / "runs" / "manifest.json",
        repository_root=repository,
    ) == output / "ml_research" / "runs" / "manifest.json"


def test_exact_repository_output_mountpoint_junction_is_supported(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    storage = tmp_path / "owner-configured-storage"
    _make_true_junction(repository / "output", storage)

    assert resolve_repository_output_root(repository) == storage.resolve()
    assert resolve_repository_output_path(
        repository / "output" / "paper" / "receipt.json",
        repository_root=repository,
    ) == storage / "paper" / "receipt.json"


def test_output_symlink_is_not_accepted_as_the_storage_boundary(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    output = repository / "output"
    try:
        output.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    with pytest.raises(
        RepositoryOutputBoundaryError,
        match="mount-point junction|reparse tag",
    ):
        resolve_repository_output_root(repository)


def test_other_location_and_nested_junction_are_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "output").mkdir(parents=True)
    outside = tmp_path / "outside"
    nested = repository / "output" / "nested"
    _make_true_junction(nested, outside)

    with pytest.raises(RepositoryOutputBoundaryError, match="symlink or junction"):
        resolve_repository_output_path(
            nested / "escape.json",
            repository_root=repository,
        )
    with pytest.raises(RepositoryOutputBoundaryError, match="lexically inside"):
        resolve_repository_output_path(
            repository / "elsewhere" / "escape.json",
            repository_root=repository,
        )


def test_output_junction_target_cannot_itself_be_another_junction(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    real_storage = tmp_path / "real-storage"
    alias_target = tmp_path / "alias-target"
    _make_true_junction(alias_target, real_storage)
    _make_true_junction(repository / "output", alias_target)

    with pytest.raises(RepositoryOutputBoundaryError, match="symlink or junction"):
        resolve_repository_output_root(repository)
