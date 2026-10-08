"""官方對照保存根只接受明示設定，且不得指向 frozen 包內。"""
import json
from pathlib import Path

import pytest

from app_module.application_bootstrap import apply_application_settings, resolve_application_settings
from data_module.config import TWStockConfig

KEY = "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT"


@pytest.mark.parametrize("via_json", [False, True])
def test_read_root_reaches_config_without_creating_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, via_json: bool) -> None:
    source = tmp_path / "saved_official"
    values = {KEY: str(source), "DATA_ROOT": str(tmp_path / "data"), "OUTPUT_ROOT": str(tmp_path / "output")}
    env = {"LOCALAPPDATA": str(tmp_path / "local")}
    if via_json:
        config_file = tmp_path / "portable.json"
        config_file.write_text(json.dumps(values), encoding="utf-8")
        env["BALDR_CONFIG"] = str(config_file)
    else:
        env.update(values)
    settings = resolve_application_settings(environ=env, resource_root=tmp_path / "bundle", frozen=False)
    for key, value in settings.environment.items():
        monkeypatch.setenv(key, value)
    config = TWStockConfig()
    assert config.technical_official_disposition_read_root == source
    assert not source.exists()


@pytest.mark.parametrize("value", ["", "   ", "relative/source"])
def test_invalid_explicit_root_is_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match=KEY):
        resolve_application_settings(environ={KEY: value, "LOCALAPPDATA": str(tmp_path)}, frozen=False)


def test_unset_root_stays_unset(tmp_path: Path) -> None:
    settings = resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path)}, frozen=False)
    assert KEY not in settings.environment


def test_frozen_root_rejected_during_resolve_and_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = tmp_path / "bundle"
    env = {"LOCALAPPDATA": str(tmp_path / "local"), KEY: str(bundle / "source")}
    with pytest.raises(ValueError, match=KEY):
        resolve_application_settings(environ=env, resource_root=bundle, frozen=True)
    settings = resolve_application_settings(environ=env, resource_root=bundle, frozen=False)
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(ValueError, match=KEY):
        apply_application_settings(settings)
