from __future__ import annotations

import json
from pathlib import Path

import pytest

import ml_module.bounded_restated_research_consumer as consumer
from ml_module.bounded_restated_research_consumer import (
    BoundedRestatedResearchError,
)


class _ReachedPublicationLoad(Exception):
    pass


def _isolated_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr(
        consumer,
        "_ml_research_repository_root",
        lambda: repository,
    )
    return repository


def _configure_active_root(repository: Path, active_root: Path) -> None:
    config_path = repository / "output" / "ml_research_storage.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_root),
            }
        ),
        encoding="utf-8",
    )


def _stop_at_publication_load(_publication_dir: Path) -> None:
    raise _ReachedPublicationLoad


def test_fit_allows_configured_active_root_before_loading_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = _isolated_repository(monkeypatch, tmp_path)
    active_root = tmp_path / "active_ml_research"
    output_dir = active_root / "fit-run"
    _configure_active_root(repository, active_root)
    monkeypatch.setattr(
        consumer,
        "load_bounded_restated_research_dataset",
        _stop_at_publication_load,
    )

    with pytest.raises(_ReachedPublicationLoad):
        consumer.fit_bounded_restated_research(
            publication_dir=tmp_path / "publication",
            output_directory=output_dir,
        )

    assert not active_root.exists()


def test_fit_rejects_legacy_root_with_active_root_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = _isolated_repository(monkeypatch, tmp_path)
    active_root = tmp_path / "active_ml_research"
    _configure_active_root(repository, active_root)
    legacy_root = repository / "output" / "ml_research"
    output_dir = legacy_root / "fit-run"

    def fail_if_publication_is_loaded(_publication_dir: Path) -> None:
        pytest.fail("the publication loader must not run for a rejected output root")

    monkeypatch.setattr(
        consumer,
        "load_bounded_restated_research_dataset",
        fail_if_publication_is_loaded,
    )

    with pytest.raises(
        BoundedRestatedResearchError,
        match="configured active ML research root",
    ):
        consumer.fit_bounded_restated_research(
            publication_dir=tmp_path / "publication",
            output_directory=output_dir,
        )

    assert not legacy_root.exists()
    assert not output_dir.exists()
    assert not active_root.exists()


def test_fit_keeps_legacy_default_when_storage_config_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = _isolated_repository(monkeypatch, tmp_path)
    legacy_output = repository / "output" / "ml_research" / "fit-run"
    monkeypatch.setattr(
        consumer,
        "load_bounded_restated_research_dataset",
        _stop_at_publication_load,
    )

    with pytest.raises(_ReachedPublicationLoad):
        consumer.fit_bounded_restated_research(
            publication_dir=tmp_path / "publication",
            output_directory=legacy_output,
        )

    assert not (repository / "output" / "ml_research_storage.json").exists()
    assert not legacy_output.parent.parent.exists()
