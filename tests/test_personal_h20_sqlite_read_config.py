from __future__ import annotations

import json
from pathlib import Path

import pytest

from app_module.application_bootstrap import (
    apply_application_settings,
    resolve_application_settings,
)
from data_module.config import TWStockConfig


_KEY = "PERSONAL_H20_SQLITE_READ_ROOT"


def _base_environment(tmp_path: Path) -> dict[str, str]:
    return {
        "LOCALAPPDATA": str(tmp_path / "local"),
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
    }


def test_unset_root_stays_none_and_explicit_root_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "private" / "h20-read"
    environment = _base_environment(tmp_path)

    settings = resolve_application_settings(environ=environment, frozen=False)
    assert settings.environment.get(_KEY) is None

    configured = resolve_application_settings(
        environ={**environment, _KEY: str(private_root)}, frozen=False
    )
    assert configured.environment[_KEY] == str(private_root.resolve())
    assert not private_root.exists()

    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "twstock-data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "twstock-output"))
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv(_KEY, str(private_root))
    config = TWStockConfig()
    assert config.personal_h20_sqlite_read_root == private_root
    assert not private_root.exists()

    # 套用其他 runtime 設定時也不建立這個外部唯讀副本根。
    apply_application_settings(configured)
    assert not private_root.exists()
    configured_app = TWStockConfig()
    assert configured_app.personal_h20_sqlite_read_root == private_root
    assert not private_root.exists()


@pytest.mark.parametrize("value", ["", "   "])
def test_explicit_empty_root_fails_closed(
    tmp_path: Path, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {**_base_environment(tmp_path), _KEY: value}
    with pytest.raises(ValueError, match=_KEY):
        resolve_application_settings(environ=environment, frozen=False)

    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv(_KEY, value)
    with pytest.raises(ValueError, match=_KEY):
        TWStockConfig()


def test_relative_root_is_rejected_by_environment_and_portable_config(
    tmp_path: Path,
) -> None:
    environment = {**_base_environment(tmp_path), _KEY: "relative/h20"}
    with pytest.raises(ValueError, match="絕對路徑"):
        resolve_application_settings(environ=environment, frozen=False)

    config_path = tmp_path / "portable" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({_KEY: "relative/h20"}), encoding="utf-8")
    with pytest.raises(ValueError, match="絕對路徑"):
        resolve_application_settings(
            environ={**_base_environment(tmp_path), "BALDR_CONFIG": str(config_path)},
            frozen=False,
        )


def test_portable_config_reads_explicit_root_without_creating_it(tmp_path: Path) -> None:
    private_root = tmp_path / "private" / "h20"
    config_path = tmp_path / "portable" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({_KEY: str(private_root)}), encoding="utf-8")

    settings = resolve_application_settings(
        environ={**_base_environment(tmp_path), "BALDR_CONFIG": str(config_path)},
        frozen=False,
    )

    assert settings.environment[_KEY] == str(private_root.resolve())
    assert not private_root.exists()


def test_frozen_settings_require_the_h20_root_outside_the_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    external = tmp_path / "external" / "h20"
    base = _base_environment(tmp_path)

    accepted = resolve_application_settings(
        environ={**base, _KEY: str(external)},
        resource_root=bundle,
        frozen=True,
    )
    assert accepted.environment[_KEY] == str(external.resolve())

    with pytest.raises(ValueError, match="frozen 程式包之外"):
        resolve_application_settings(
            environ={**base, _KEY: str(bundle / "private" / "h20")},
            resource_root=bundle,
            frozen=True,
        )
