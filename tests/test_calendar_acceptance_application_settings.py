"""正常Main只讀settings固定的日曆接受；所有接受為明示合成fixture。"""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys

import pytest

from app_module.application_bootstrap import (
    apply_application_settings, configured_portfolio_calendar_acceptance_binding,
    resolve_application_settings,
)
from app_module.recommendation_portfolio_calendar_acceptance_binding_v1 import serialize_portfolio_calendar_acceptance_binding_v1
from test_portfolio_calendar_acceptance_binding_v1 import _anchors


PATH_KEY = "CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH"
HASH_KEY = "CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256"


def _env(root):
    return {"LOCALAPPDATA": str(root / "local"), "DATA_ROOT": str(root / "market"),
            "OUTPUT_ROOT": str(root / "output"), "BALDR_CONFIG": str(root / "not-created-config.json")}


def _saved(tmp_path):
    path = tmp_path / "acceptance.json"
    raw = serialize_portfolio_calendar_acceptance_binding_v1(_anchors())
    path.write_bytes(raw)
    return path, sha256(raw).hexdigest()


def _load(settings, root):
    return configured_portfolio_calendar_acceptance_binding(settings, protected_roots=(root / "formal",))


def test_absent_binding_and_settings_resolution_do_not_read_or_create_sources(tmp_path):
    settings = resolve_application_settings(environ=_env(tmp_path), frozen=False)
    assert _load(settings, tmp_path) is None
    assert not (tmp_path / "local").exists() and not (tmp_path / "market").exists()
    missing = tmp_path / "not-created-acceptance.json"
    settings = resolve_application_settings(environ={**_env(tmp_path), PATH_KEY: str(missing), HASH_KEY: "a"*64}, frozen=False)
    assert settings.environment[PATH_KEY] == str(missing) and not missing.exists()
    with pytest.raises(ValueError):
        _load(settings, tmp_path)


@pytest.mark.parametrize("case", ["path_only", "hash_only", "blank_path", "blank_hash", "relative_path", "uppercase_hash", "short_hash"])
def test_incomplete_setting_rejected_before_runtime_write(tmp_path, case):
    env = {**_env(tmp_path), PATH_KEY: str(tmp_path / "binding.json"), HASH_KEY: "a"*64}
    if case == "path_only": del env[HASH_KEY]
    elif case == "hash_only": del env[PATH_KEY]
    elif case == "blank_path": env[PATH_KEY] = " "
    elif case == "blank_hash": env[HASH_KEY] = " "
    elif case == "relative_path": env[PATH_KEY] = "binding.json"
    elif case == "uppercase_hash": env[HASH_KEY] = "A"*64
    elif case == "short_hash": env[HASH_KEY] = "a"*63
    with pytest.raises(ValueError):
        resolve_application_settings(environ=env, frozen=False)
    assert not (tmp_path / "market").exists() and not (tmp_path / "output").exists()


def test_loader_uses_frozen_settings_instead_of_mutable_environment(tmp_path, monkeypatch):
    path, digest = _saved(tmp_path)
    env = {**_env(tmp_path), PATH_KEY: str(path), HASH_KEY: digest}
    settings = resolve_application_settings(environ=env, frozen=False)
    env[HASH_KEY] = "0"*64
    monkeypatch.setenv(PATH_KEY, str(tmp_path / "wrong.json"))
    monkeypatch.setenv(HASH_KEY, "0"*64)
    assert _load(settings, tmp_path).trusted_acceptances == _anchors()
    assert settings.to_dict()["environment"][HASH_KEY] == digest
    changed = replace(settings, environment={**settings.environment, HASH_KEY: "0"*64})
    with pytest.raises(ValueError, match="external_sha256_mismatch"):
        _load(changed, tmp_path)


def test_frozen_bundle_binding_is_rejected_in_settings_and_loader(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    path, digest = _saved(bundle)
    env = {**_env(tmp_path), PATH_KEY: str(path), HASH_KEY: digest}
    with pytest.raises(ValueError, match="frozen"):
        resolve_application_settings(environ=env, resource_root=bundle, frozen=True)
    settings = resolve_application_settings(environ=env, resource_root=bundle, frozen=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(ValueError, match="protected_or_formal_root"):
        _load(settings, tmp_path)


def test_binding_alias_is_not_resolved_away_by_settings(tmp_path, monkeypatch):
    path = tmp_path / "alias.json"
    original_resolve = Path.resolve

    def observed(candidate, *args, **kwargs):
        if candidate == path:
            pytest.fail("設定階段不得消除binding的alias身分")
        return original_resolve(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", observed)
    settings = resolve_application_settings(environ={**_env(tmp_path), PATH_KEY: str(path), HASH_KEY: "a"*64}, frozen=False)
    assert settings.environment[PATH_KEY] == str(path)


def test_apply_preserves_pinned_pair_and_does_not_read_binding(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os, "environ", dict(os.environ))
    path = tmp_path / "missing.json"
    settings = resolve_application_settings(environ={**_env(tmp_path), PATH_KEY: str(path), HASH_KEY: "a"*64}, frozen=False)
    monkeypatch.delenv(PATH_KEY, raising=False)
    monkeypatch.delenv(HASH_KEY, raising=False)
    apply_application_settings(settings)
    assert os.environ[PATH_KEY] == str(path) and os.environ[HASH_KEY] == "a"*64
    assert not path.exists()
