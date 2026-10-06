"""Baldr Python 與 frozen 入口共用的純設定解析契約。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


_PORTABLE_KEYS = frozenset(
    {
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "RESEARCH_STATE_ROOT",
        "PERSONAL_DATA_ROOT",
        "PERSONAL_WATCHLIST_SOURCE",
        "PERSONAL_JOURNAL_ROOT",
        "PERSONAL_JOURNAL_MODE",
        "PERSONAL_STORE_ROOT",
        "PERSONAL_STORE_MODE",
        "PERSONAL_MODEL_POLICY_PATH",
    }
)
_MAX_CONFIG_BYTES = 64 * 1024


@dataclass(frozen=True)
class ApplicationSettings:
    """已解析的應用程式路徑與環境設定快照。"""

    config_path: Path
    configured: bool
    environment: dict[str, str]
    resource_root: Path
    runtime_state_root: Path
    ml_registry_repository_root: Path

    def __post_init__(self) -> None:
        # 複製來源 mapping，避免建立設定後來源 dict 的變化滲入快照。
        object.__setattr__(self, "environment", dict(self.environment))

    def to_dict(self) -> dict[str, Any]:
        """回傳可供 JSON 序列化的設定說明。"""

        return {
            "config_path": str(self.config_path),
            "configured": self.configured,
            "environment": dict(self.environment),
            "resource_root": str(self.resource_root),
            "runtime_state_root": str(self.runtime_state_root),
            "ml_registry_repository_root": str(self.ml_registry_repository_root),
        }


def resolve_application_settings(
    *,
    environ: Mapping[str, str] | None = None,
    resource_root: Path | None = None,
    frozen: bool | None = None,
) -> ApplicationSettings:
    """純解析 Baldr 設定，不建立目錄、不修改 ``os.environ``。"""

    source = os.environ if environ is None else environ
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not isinstance(is_frozen, bool):
        raise ValueError("frozen 必須是布林值")

    local_app_data = _optional_environment_path(source, "LOCALAPPDATA")
    local_base = local_app_data or Path.home()
    if not local_base.is_absolute():
        raise ValueError("LOCALAPPDATA 必須是絕對路徑")
    application_home = _canonical_path(local_base / "baldr")

    config_value = _optional_environment_text(source, "BALDR_CONFIG")
    if config_value is None:
        config_path = application_home / "config.json"
    else:
        candidate = Path(config_value).expanduser()
        config_path = candidate if candidate.is_absolute() else Path.cwd() / candidate
        config_path = _canonical_path(config_path)

    json_values: dict[str, str] = {}
    configured_by_file = config_path.is_file()
    if config_path.exists() and not configured_by_file:
        raise ValueError(f"Baldr 設定路徑不是一般檔案：{config_path}")
    if configured_by_file:
        json_values = _read_portable_config(config_path)

    effective: dict[str, str] = {}
    environment_values: dict[str, str] = {}
    for key in sorted(_PORTABLE_KEYS):
        value = _optional_environment_text(source, key)
        if value is not None:
            _validate_setting(key, value, origin="環境變數")
            environment_values[key] = _normalize_configured_path(key, value)
        elif key in json_values:
            environment_values[key] = json_values[key]

    effective.update(json_values)
    effective.update(environment_values)
    configured_by_environment = all(
        key in environment_values for key in ("DATA_ROOT", "OUTPUT_ROOT")
    )
    configured = configured_by_file or configured_by_environment

    data_root = _configured_root(effective, "DATA_ROOT", application_home / "market")
    output_root = _configured_root(effective, "OUTPUT_ROOT", application_home / "output")
    effective["DATA_ROOT"] = str(data_root)
    effective["OUTPUT_ROOT"] = str(output_root)

    runtime_state_root = _canonical_path(output_root / "application_state")
    mplconfig_value = _optional_environment_path(source, "MPLCONFIGDIR")
    mplconfig_path = mplconfig_value or runtime_state_root / "matplotlib"
    effective["MPLCONFIGDIR"] = str(_canonical_path(mplconfig_path))
    effective["PYTHONUTF8"] = (
        _optional_environment_text(source, "PYTHONUTF8") or "1"
    )
    effective["PYTHONIOENCODING"] = (
        _optional_environment_text(source, "PYTHONIOENCODING") or "utf-8"
    )
    effective["BALDR_CONFIG"] = str(config_path)

    if resource_root is None:
        if is_frozen:
            frozen_resource_root = getattr(sys, "_MEIPASS", None)
            if frozen_resource_root:
                selected_resource_root = Path(frozen_resource_root)
            elif getattr(sys, "executable", None):
                selected_resource_root = Path(sys.executable).parent
            else:
                selected_resource_root = Path(__file__).resolve().parents[1]
        else:
            selected_resource_root = Path(__file__).resolve().parents[1]
    else:
        selected_resource_root = Path(resource_root)
    selected_resource_root = _canonical_path(selected_resource_root)

    ml_registry_root = _configured_root(
        effective, "RESEARCH_STATE_ROOT", application_home / "research_state"
    )
    effective["RESEARCH_STATE_ROOT"] = str(ml_registry_root)
    _validate_research_isolation(ml_registry_root, data_root)
    if is_frozen:
        bundle_roots = _frozen_bundle_roots(selected_resource_root)
        for name, path in (
            ("DATA_ROOT", data_root),
            ("OUTPUT_ROOT", output_root),
            ("MPLCONFIGDIR", Path(effective["MPLCONFIGDIR"])),
            ("研究 registry 根目錄", ml_registry_root),
        ):
            if any(_is_same_or_child(path, bundle) for bundle in bundle_roots):
                raise ValueError(f"{name} 必須位於 frozen 程式包之外")

    return ApplicationSettings(
        config_path=config_path,
        configured=configured,
        environment=effective,
        resource_root=selected_resource_root,
        runtime_state_root=runtime_state_root,
        ml_registry_repository_root=ml_registry_root,
    )


def apply_application_settings(settings: ApplicationSettings) -> None:
    """明確套用環境設定並建立外部 runtime 目錄，不接觸資料庫或模型。"""

    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是 ApplicationSettings")
    environment = dict(settings.environment)
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ValueError("environment 的鍵和值都必須是字串")
    if "DATA_ROOT" not in environment or "OUTPUT_ROOT" not in environment:
        raise ValueError("environment 必須包含 DATA_ROOT 與 OUTPUT_ROOT")

    data_root = _absolute_environment_path("DATA_ROOT", environment["DATA_ROOT"])
    output_root = _absolute_environment_path("OUTPUT_ROOT", environment["OUTPUT_ROOT"])
    runtime_root = _canonical_path(settings.runtime_state_root)
    registry_root = _absolute_environment_path(
        "RESEARCH_STATE_ROOT",
        environment.get("RESEARCH_STATE_ROOT", str(settings.ml_registry_repository_root)),
    )
    if registry_root != _canonical_path(settings.ml_registry_repository_root):
        raise ValueError("RESEARCH_STATE_ROOT 必須與 ml_registry_repository_root 相同")
    mplconfig_root = _absolute_environment_path(
        "MPLCONFIGDIR",
        environment.get("MPLCONFIGDIR", str(runtime_root / "matplotlib")),
    )
    _validate_research_isolation(registry_root, data_root)
    if runtime_root != _canonical_path(output_root / "application_state"):
        raise ValueError("runtime_state_root 必須位於 OUTPUT_ROOT/application_state")

    if bool(getattr(sys, "frozen", False)):
        bundles = _frozen_bundle_roots(_canonical_path(settings.resource_root))
        for name, path in (
            ("DATA_ROOT", data_root),
            ("OUTPUT_ROOT", output_root),
            ("MPLCONFIGDIR", mplconfig_root),
            ("研究 registry 根目錄", registry_root),
        ):
            if any(_is_same_or_child(path, bundle) for bundle in bundles):
                raise ValueError(f"{name} 必須位於 frozen 程式包之外")

    for directory in (runtime_root, registry_root, mplconfig_root):
        directory.mkdir(parents=True, exist_ok=True)
    os.environ.update(environment)


def _read_portable_config(path: Path) -> dict[str, str]:
    try:
        if path.stat().st_size > _MAX_CONFIG_BYTES:
            raise ValueError("Baldr 設定檔超過允許大小")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Baldr 設定檔不是有效 UTF-8 JSON：{path}") from exc
    except ValueError as exc:
        if str(exc) == "Baldr 設定檔超過允許大小":
            raise
        raise ValueError(f"Baldr 設定檔不是有效 UTF-8 JSON：{path}") from exc

    if not isinstance(payload, dict) or set(payload) - _PORTABLE_KEYS:
        raise ValueError("config.json 含非物件內容或未支援的設定")
    values: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} 必須是非空字串")
        _validate_setting(key, value, origin="config.json")
        values[key] = _normalize_configured_path(key, value)
    return values


def _validate_setting(key: str, value: str, *, origin: str) -> None:
    if not value.strip():
        raise ValueError(f"{origin} 的 {key} 必須是非空字串")
    if key.endswith(("ROOT", "PATH", "SOURCE")) and not Path(value).is_absolute():
        raise ValueError(f"{origin} 的 {key} 必須是絕對路徑")


def _normalize_configured_path(key: str, value: str) -> str:
    if key.endswith(("ROOT", "PATH", "SOURCE")):
        return str(_canonical_path(Path(value)))
    return value


def _optional_environment_text(environ: Mapping[str, str], key: str) -> str | None:
    if key not in environ:
        return None
    value = environ[key]
    if not isinstance(value, str):
        raise ValueError(f"環境變數 {key} 必須是字串")
    return value if value.strip() else None


def _optional_environment_path(environ: Mapping[str, str], key: str) -> Path | None:
    value = _optional_environment_text(environ, key)
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"環境變數 {key} 必須是絕對路徑")
    return _canonical_path(path)


def _configured_root(values: Mapping[str, str], key: str, default: Path) -> Path:
    value = values.get(key)
    return _canonical_path(Path(value)) if value is not None else _canonical_path(default)


def _absolute_environment_path(key: str, value: str) -> Path:
    if not value.strip():
        raise ValueError(f"{key} 必須是非空絕對路徑")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{key} 必須是絕對路徑")
    return _canonical_path(path)


def _canonical_path(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


def _frozen_bundle_roots(resource_root: Path) -> tuple[Path, ...]:
    roots = {_canonical_path(resource_root)}
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.add(_canonical_path(Path(meipass)))
    executable = getattr(sys, "executable", None)
    if executable:
        roots.add(_canonical_path(Path(executable).parent))
    return tuple(roots)


def _validate_research_isolation(registry_root: Path, data_root: Path) -> None:
    if _paths_overlap(registry_root, data_root):
        raise ValueError("ML research registry 根目錄必須與 DATA_ROOT 隔離")


def _paths_overlap(left: Path, right: Path) -> bool:
    left_key = os.path.normcase(str(_canonical_path(left))).rstrip("\\/").casefold()
    right_key = os.path.normcase(str(_canonical_path(right))).rstrip("\\/").casefold()
    return (
        left_key == right_key
        or left_key.startswith(right_key + os.sep.casefold())
        or right_key.startswith(left_key + os.sep.casefold())
    )


def _is_same_or_child(path: Path, parent: Path) -> bool:
    path_key = os.path.normcase(str(_canonical_path(path))).rstrip("\\/").casefold()
    parent_key = os.path.normcase(str(_canonical_path(parent))).rstrip("\\/").casefold()
    return path_key == parent_key or path_key.startswith(parent_key + os.sep.casefold())


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 不可包含重複鍵")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 不支援常數：{value}")
