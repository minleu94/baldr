"""正常啟動的精確cohort設定與外部接受錨點，不把設定自洽當來源品質。"""
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys

import pytest

from app_module.application_bootstrap import (
    apply_application_settings, configured_daily_monthly_revenue_cohort_reader,
    resolve_application_settings,
)
from data_module.daily_monthly_revenue_cohort import write_daily_monthly_revenue_cohort_pin_create_only
from data_module.daily_monthly_revenue_cohort_binding import serialize_daily_monthly_revenue_cohort_binding

PATH_KEY = 'MONTHLY_REVENUE_COHORT_BINDING_PATH'
HASH_KEY = 'MONTHLY_REVENUE_COHORT_BINDING_SHA256'


def _environment(root):
    return {'LOCALAPPDATA': str(root/'local'), 'DATA_ROOT': str(root/'market'),
            'OUTPUT_ROOT': str(root/'output'), 'BALDR_CONFIG': str(root/'config.json')}


def _saved_binding(root):
    root.mkdir()
    fixture = runpy.run_path(str(Path(__file__).with_name('test_recommendation_monthly_revenue_cohort.py')))
    _, pin, _, readers, _, _ = fixture['_fixture'](root)
    pin_root = root/'cohort-pins'
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    raw = serialize_daily_monthly_revenue_cohort_binding(cohort_pin_root=pin_root, pin=pin, market_readers=readers)
    binding_path = root/'explicit-binding.json'
    with binding_path.open('xb') as handle:
        handle.write(raw)
    return pin, binding_path, sha256(raw).hexdigest()


def test_settings_resolve_is_pure_and_legacy_does_not_select_cohort(tmp_path):
    settings = resolve_application_settings(environ=_environment(tmp_path), frozen=False)
    assert PATH_KEY not in settings.environment and HASH_KEY not in settings.environment
    assert configured_daily_monthly_revenue_cohort_reader(settings) is None
    assert not (tmp_path/'local').exists() and not (tmp_path/'market').exists()
    selected = {**_environment(tmp_path), PATH_KEY: str(tmp_path/'not-created.json'), HASH_KEY: 'a'*64}
    settings = resolve_application_settings(environ=selected, frozen=False)
    assert settings.environment[PATH_KEY] == str((tmp_path/'not-created.json').resolve())
    assert settings.environment[HASH_KEY] == 'a'*64 and not (tmp_path/'not-created.json').exists()
    with pytest.raises((ValueError, OSError)):
        configured_daily_monthly_revenue_cohort_reader(settings)


def test_binding_path_not_resolved_before_loader_can_reject_alias(tmp_path, monkeypatch):
    artifact = tmp_path/'external-alias.json'
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == artifact:
            raise AssertionError('設定層不得消除binding alias身分')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', resolve)
    settings = resolve_application_settings(
        environ={**_environment(tmp_path), PATH_KEY: str(artifact), HASH_KEY: 'a'*64}, frozen=False,
    )
    assert settings.environment[PATH_KEY] == str(artifact)


@pytest.mark.parametrize('case', ('path_only', 'hash_only', 'blank_path', 'blank_hash', 'relative_path', 'uppercase_hash', 'short_hash'))
def test_partial_or_invalid_cohort_setting_rejected_before_runtime_write(tmp_path, case):
    env = {**_environment(tmp_path), PATH_KEY: str(tmp_path/'binding.json'), HASH_KEY: 'a'*64}
    if case == 'path_only':
        del env[HASH_KEY]
    elif case == 'hash_only':
        del env[PATH_KEY]
    elif case == 'blank_path':
        env[PATH_KEY] = ' '
    elif case == 'blank_hash':
        env[HASH_KEY] = ' '
    elif case == 'relative_path':
        env[PATH_KEY] = 'binding.json'
    elif case == 'uppercase_hash':
        env[HASH_KEY] = 'A'*64
    else:
        env[HASH_KEY] = 'a'*63
    with pytest.raises(ValueError):
        resolve_application_settings(environ=env, frozen=False)
    assert not (tmp_path/'output').exists() and not (tmp_path/'market').exists()


def test_portable_json_survives_fresh_settings_and_external_binding_exact(tmp_path):
    pin, binding_path, digest = _saved_binding(tmp_path/'source')
    config = {key: value for key, value in _environment(tmp_path).items() if key in ('DATA_ROOT', 'OUTPUT_ROOT')}
    config.update({PATH_KEY: str(binding_path), HASH_KEY: digest})
    (tmp_path/'config.json').write_text(json.dumps(config), encoding='utf-8')
    env = {'LOCALAPPDATA': str(tmp_path/'local'), 'BALDR_CONFIG': str(tmp_path/'config.json')}
    settings = resolve_application_settings(environ=env, frozen=False)
    first = configured_daily_monthly_revenue_cohort_reader(settings)
    second = configured_daily_monthly_revenue_cohort_reader(resolve_application_settings(environ=env, frozen=False))
    assert first is not None and second is not None and first is not second
    assert first.pin == second.pin == pin
    assert len(first.verify_cohort()) == len(second.verify_cohort()) == 2
    changed = resolve_application_settings(environ={**env, HASH_KEY: '0'*64}, frozen=False)
    with pytest.raises(ValueError):
        configured_daily_monthly_revenue_cohort_reader(changed)
    assert not (tmp_path/'market').exists() and not (tmp_path/'output').exists()


def test_frozen_binding_and_nested_source_must_be_external(tmp_path, monkeypatch):
    bundle = tmp_path/'bundle'
    bundle.mkdir()
    env = {**_environment(tmp_path), PATH_KEY: str(bundle/'binding.json'), HASH_KEY: 'a'*64}
    with pytest.raises(ValueError, match='frozen'):
        resolve_application_settings(environ=env, resource_root=bundle, frozen=True)
    pin, binding_path, digest = _saved_binding(bundle/'source')
    outside = tmp_path/'binding.json'
    outside.write_bytes(binding_path.read_bytes())
    settings = resolve_application_settings(environ={**_environment(tmp_path), PATH_KEY: str(outside), HASH_KEY: digest}, resource_root=bundle, frozen=True)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    with pytest.raises(ValueError):
        configured_daily_monthly_revenue_cohort_reader(settings)
    assert pin.required_markets == ('twse', 'tpex')


def test_apply_revalidates_partial_mutated_snapshot_without_creating_runtime(tmp_path):
    settings = resolve_application_settings(environ=_environment(tmp_path), frozen=False)
    settings.environment[HASH_KEY] = 'a'*64
    with pytest.raises(ValueError):
        apply_application_settings(settings)
    assert not settings.runtime_state_root.exists()
