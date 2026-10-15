"""純設定、外部系列錨點及 invocation-local 選版的正常 composition 契約。"""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

from app_module.application_bootstrap import (
    resolve_application_settings, apply_application_settings,
    configured_daily_monthly_revenue_series_reader_factory,
    configured_daily_monthly_revenue_exact_pin_reader_factory,
)
from tests.test_monthly_revenue_cohort_application_settings import _environment
from tests.test_daily_monthly_revenue_series_binding import _fixture

PATH_KEY = "MONTHLY_REVENUE_SERIES_BINDING_PATH"
HASH_KEY = "MONTHLY_REVENUE_SERIES_BINDING_SHA256"


def test_resolve_and_factory_creation_are_pure_and_freeze_settings_anchor(tmp_path):
    path = tmp_path / "not-created.json"
    settings = resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(path), HASH_KEY: "a" * 64}, frozen=False)
    factory = configured_daily_monthly_revenue_series_reader_factory(settings)
    assert callable(factory) and not path.exists() and not settings.runtime_state_root.exists()
    fixture_root = tmp_path / "sources"
    fixture_root.mkdir()
    fixture = _fixture(fixture_root)
    settings.environment[PATH_KEY] = str(fixture["binding_path"])
    settings.environment[HASH_KEY] = fixture["binding_sha"]
    with pytest.raises(ValueError):
        factory(fixture["pins"][0].available_hour)
    selected = configured_daily_monthly_revenue_series_reader_factory(settings)
    assert selected(fixture["pins"][0].available_hour).pin == fixture["pins"][0]


@pytest.mark.parametrize("case", ("path_only", "hash_only", "blank", "relative", "uppercase", "both_modes"))
def test_invalid_series_settings_fail_before_runtime_write(tmp_path, case):
    env = {**_environment(tmp_path), PATH_KEY: str(tmp_path / "binding.json"), HASH_KEY: "a" * 64}
    if case == "path_only":
        del env[HASH_KEY]
    elif case == "hash_only":
        del env[PATH_KEY]
    elif case == "blank":
        env[PATH_KEY] = " "
    elif case == "relative":
        env[PATH_KEY] = "binding.json"
    elif case == "uppercase":
        env[HASH_KEY] = "A" * 64
    else:
        env.update(MONTHLY_REVENUE_COHORT_BINDING_PATH=str(tmp_path / "fixed.json"), MONTHLY_REVENUE_COHORT_BINDING_SHA256="b" * 64)
    with pytest.raises(ValueError):
        resolve_application_settings(environ=env, frozen=False)
    assert not (tmp_path / "output").exists() and not (tmp_path / "market").exists()


def test_series_alias_path_is_not_canonicalized_before_loader(tmp_path, monkeypatch):
    path = tmp_path / "alias.json"
    original = Path.resolve
    def guarded(candidate, *args, **kwargs):
        if candidate == path:
            raise AssertionError("binding alias must survive configuration")
        return original(candidate, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", guarded)
    settings = resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(path), HASH_KEY: "a" * 64}, frozen=False)
    assert settings.environment[PATH_KEY] == str(path)


def test_frozen_series_binding_and_mutated_apply_are_revalidated(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    with pytest.raises(ValueError, match="frozen"):
        resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(bundle / "binding.json"), HASH_KEY: "a" * 64}, resource_root=bundle, frozen=True)
    settings = resolve_application_settings(environ=_environment(tmp_path), frozen=False)
    settings.environment[HASH_KEY] = "a" * 64
    with pytest.raises(ValueError):
        apply_application_settings(settings)
    assert not settings.runtime_state_root.exists()


def test_no_series_configuration_preserves_legacy_composition(tmp_path):
    settings = resolve_application_settings(environ=_environment(tmp_path), frozen=False)
    assert configured_daily_monthly_revenue_series_reader_factory(settings) is None
    assert configured_daily_monthly_revenue_exact_pin_reader_factory(settings) is None


def test_exact_saved_pin_uses_trust_without_reading_mutable_selection_files(tmp_path):
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    settings = resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(fixture["binding_path"]), HASH_KEY: fixture["binding_sha"]}, frozen=False)
    exact = configured_daily_monthly_revenue_exact_pin_reader_factory(settings)
    fixture["pointer_path"].unlink()
    fixture["catalog_path"].unlink()
    reader = exact(pin, pin.available_hour)
    assert reader.pin == pin and len(reader.verify_cohort()) == 2
    with pytest.raises(ValueError):
        configured_daily_monthly_revenue_series_reader_factory(settings)(pin.available_hour)


def test_exact_saved_pin_still_denies_future_wrong_scope_and_missing_original(tmp_path):
    from datetime import timedelta
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    settings = resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(fixture["binding_path"]), HASH_KEY: fixture["binding_sha"]}, frozen=False)
    exact = configured_daily_monthly_revenue_exact_pin_reader_factory(settings)
    with pytest.raises(ValueError):
        exact(pin, pin.available_hour - timedelta(microseconds=1))
    (fixture["trust"].cohort_pin_root / f"{pin.cohort_sha256}.json").unlink()
    with pytest.raises(ValueError):
        exact(pin, pin.available_hour)
