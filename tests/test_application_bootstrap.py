from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from app_module.application_bootstrap import (
    ApplicationSettings,
    apply_application_settings,
    resolve_application_settings,
)


def _environment(tmp_path: Path) -> dict[str, str]:
    return {"LOCALAPPDATA": str(tmp_path / "local")}


def test_environment_overrides_portable_json_and_serializes_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "portable.json"
    config_path.write_text(
        json.dumps(
            {
                "DATA_ROOT": str(tmp_path / "json-market"),
                "OUTPUT_ROOT": str(tmp_path / "json-output"),
                "RESEARCH_STATE_ROOT": str(tmp_path / "json-research"),
                "PERSONAL_MODEL_POLICY_PATH": str(tmp_path / "policy.json"),
            }
        ),
        encoding="utf-8",
    )
    environ = {
        **_environment(tmp_path),
        "BALDR_CONFIG": str(config_path),
        "DATA_ROOT": str(tmp_path / "environment-market"),
        "RESEARCH_STATE_ROOT": str(tmp_path / "environment-research"),
        "PERSONAL_MODEL_POLICY_PATH": str(tmp_path / "environment-policy.json"),
    }

    settings = resolve_application_settings(environ=environ, resource_root=tmp_path / "repo")

    assert settings.configured is True
    assert settings.environment["DATA_ROOT"] == str(tmp_path / "environment-market")
    assert settings.environment["OUTPUT_ROOT"] == str(tmp_path / "json-output")
    assert settings.ml_registry_repository_root == tmp_path / "environment-research"
    assert settings.environment["RESEARCH_STATE_ROOT"] == str(
        tmp_path / "environment-research"
    )
    assert settings.environment["PERSONAL_MODEL_POLICY_PATH"] == str(
        tmp_path / "environment-policy.json"
    )
    assert json.loads(json.dumps(settings.to_dict()))["runtime_state_root"] == str(
        tmp_path / "json-output" / "application_state"
    )


def test_blank_environment_values_fall_through_to_json_or_shared_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "portable.json"
    config_path.write_text(
        json.dumps({"DATA_ROOT": str(tmp_path / "json-market")}), encoding="utf-8"
    )
    settings = resolve_application_settings(
        environ={
            **_environment(tmp_path),
            "BALDR_CONFIG": str(config_path),
            "DATA_ROOT": "  ",
            "OUTPUT_ROOT": "",
        }
    )

    assert settings.environment["DATA_ROOT"] == str(tmp_path / "json-market")
    assert settings.environment["OUTPUT_ROOT"] == str(tmp_path / "local" / "baldr" / "output")
    assert settings.configured is True


def test_default_roots_are_shared_and_research_state_is_separate(tmp_path: Path) -> None:
    settings = resolve_application_settings(environ=_environment(tmp_path))

    assert settings.environment["DATA_ROOT"] == str(tmp_path / "local" / "baldr" / "market")
    assert settings.environment["OUTPUT_ROOT"] == str(tmp_path / "local" / "baldr" / "output")
    assert settings.runtime_state_root == tmp_path / "local" / "baldr" / "output" / "application_state"
    assert settings.ml_registry_repository_root == tmp_path / "local" / "baldr" / "research_state"
    assert settings.environment["RESEARCH_STATE_ROOT"] == str(
        tmp_path / "local" / "baldr" / "research_state"
    )
    assert settings.resource_root.is_absolute()
    assert settings.configured is False


def test_resolution_has_no_environment_or_filesystem_side_effects(
    tmp_path: Path,
) -> None:
    before_environment = dict(os.environ)
    before_cwd = Path.cwd()
    local_root = tmp_path / "new-local-root"

    settings = resolve_application_settings(
        environ={"LOCALAPPDATA": str(local_root)}, resource_root=tmp_path / "resources"
    )

    assert dict(os.environ) == before_environment
    assert Path.cwd() == before_cwd
    assert not local_root.exists()
    assert not settings.runtime_state_root.exists()
    assert not settings.ml_registry_repository_root.exists()


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        "[]",
        '{"DATA_ROOT": null}',
        '{"DATA_ROOT": "relative"}',
        '{"UNSUPPORTED": "value"}',
        '{"DATA_ROOT": "/one", "DATA_ROOT": "/two"}',
    ],
)
def test_invalid_portable_json_is_rejected(tmp_path: Path, payload: str) -> None:
    config_path = tmp_path / "portable.json"
    config_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        resolve_application_settings(
            environ={**_environment(tmp_path), "BALDR_CONFIG": str(config_path)}
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("DATA_ROOT", "relative"),
        ("RESEARCH_STATE_ROOT", "relative-research"),
        ("PERSONAL_WATCHLIST_SOURCE", "relative.csv"),
        ("PERSONAL_MODEL_POLICY_PATH", "relative-policy.json"),
        ("MPLCONFIGDIR", "relative-cache"),
    ],
)
def test_invalid_path_environment_values_are_rejected(
    tmp_path: Path, key: str, value: str
) -> None:
    with pytest.raises(ValueError):
        resolve_application_settings(environ={**_environment(tmp_path), key: value})


def test_frozen_data_and_output_roots_cannot_point_into_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "package"
    environ = {
        **_environment(tmp_path),
        "DATA_ROOT": str(bundle / "market"),
        "OUTPUT_ROOT": str(tmp_path / "external-output"),
    }

    with pytest.raises(ValueError, match="程式包之外"):
        resolve_application_settings(
            environ=environ, resource_root=bundle, frozen=True
        )


def test_frozen_without_meipass_uses_executable_directory_as_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package_root = tmp_path / "package"
    monkeypatch.setattr(sys, "executable", str(package_root / "baldr.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    settings = resolve_application_settings(
        environ=_environment(tmp_path), frozen=True
    )

    assert settings.resource_root == package_root
    assert settings.environment["DATA_ROOT"] == str(tmp_path / "local" / "baldr" / "market")


def test_research_registry_root_cannot_overlap_data_root(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    environ = {
        "LOCALAPPDATA": str(local_root),
        "DATA_ROOT": str(local_root / "baldr"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
    }

    with pytest.raises(ValueError, match="與 DATA_ROOT 隔離"):
        resolve_application_settings(environ=environ)


def test_configured_research_root_cannot_overlap_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "market"
    environ = {
        "LOCALAPPDATA": str(tmp_path / "local"),
        "DATA_ROOT": str(data_root),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "RESEARCH_STATE_ROOT": str(data_root / "research"),
    }

    with pytest.raises(ValueError, match="與 DATA_ROOT 隔離"):
        resolve_application_settings(environ=environ)


def test_configured_research_root_cannot_point_into_frozen_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "package"
    environ = {
        **_environment(tmp_path),
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "RESEARCH_STATE_ROOT": str(bundle / "research"),
    }

    with pytest.raises(ValueError, match="程式包之外"):
        resolve_application_settings(environ=environ, resource_root=bundle, frozen=True)


def test_apply_creates_only_runtime_directories_and_sets_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in (
        "BALDR_CONFIG",
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "MPLCONFIGDIR",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
    ):
        monkeypatch.delenv(key, raising=False)
    local_root = tmp_path / "isolated-local"
    settings = resolve_application_settings(
        environ={"LOCALAPPDATA": str(local_root)}, resource_root=tmp_path / "repo"
    )

    apply_application_settings(settings)

    assert isinstance(settings, ApplicationSettings)
    assert os.environ["DATA_ROOT"] == str(local_root / "baldr" / "market")
    assert os.environ["OUTPUT_ROOT"] == str(local_root / "baldr" / "output")
    assert settings.runtime_state_root.is_dir()
    assert settings.ml_registry_repository_root.is_dir()
    assert os.environ["RESEARCH_STATE_ROOT"] == str(
        local_root / "baldr" / "research_state"
    )
    assert Path(os.environ["MPLCONFIGDIR"]).is_dir()
    assert not (local_root / "baldr" / "market").exists()
    assert not list(settings.runtime_state_root.rglob("*.db"))
