from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import app_module.weekly_review_history_source as source
from app_module.personal_store_routes import PersonalStoreMode
from app_module.weekly_review_history_source import (
    WeeklyReviewHistorySourceError,
    resolve_weekly_review_working_copy_path,
)


def test_resolves_existing_nonproduction_working_copy_in_legacy_compat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = SimpleNamespace(data_root=tmp_path / "production")
    selected = tmp_path / "weekly-copy.db"
    selected.touch()
    monkeypatch.setattr(
        source,
        "resolve_personal_store_selection",
        lambda _config: SimpleNamespace(mode=PersonalStoreMode.LEGACY_COMPAT),
    )

    assert resolve_weekly_review_working_copy_path(config, selected) == selected.resolve()


def test_rejects_formal_database_path_even_when_it_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production_root = tmp_path / "production"
    formal_db = production_root / "sqlite" / "twstock.db"
    formal_db.parent.mkdir(parents=True)
    formal_db.touch()
    config = SimpleNamespace(data_root=production_root)
    monkeypatch.setattr(
        source,
        "resolve_personal_store_selection",
        lambda _config: SimpleNamespace(mode=PersonalStoreMode.LEGACY_COMPAT),
    )

    with pytest.raises(WeeklyReviewHistorySourceError, match="formal_db_forbidden"):
        resolve_weekly_review_working_copy_path(config, formal_db)


def test_rejects_custom_database_override_for_personal_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "weekly-copy.db"
    selected.touch()
    config = SimpleNamespace(data_root=tmp_path / "production")
    monkeypatch.setattr(
        source,
        "resolve_personal_store_selection",
        lambda _config: SimpleNamespace(mode=PersonalStoreMode.PERSONAL),
    )

    with pytest.raises(WeeklyReviewHistorySourceError, match="requires_legacy_compat"):
        resolve_weekly_review_working_copy_path(config, selected)


def test_rejects_missing_working_copy_without_creating_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "missing.db"
    config = SimpleNamespace(data_root=tmp_path / "production")
    monkeypatch.setattr(
        source,
        "resolve_personal_store_selection",
        lambda _config: SimpleNamespace(mode=PersonalStoreMode.LEGACY_COMPAT),
    )

    with pytest.raises(WeeklyReviewHistorySourceError, match="working_copy_not_file"):
        resolve_weekly_review_working_copy_path(config, selected)
    assert not selected.exists()
