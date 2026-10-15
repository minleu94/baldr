"""Baldr Python 與 frozen 入口共用的純設定解析契約。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING
from data_module.config import _paper_contract_artifacts_root_path_error

if TYPE_CHECKING:
    from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader, DailyMonthlyRevenueCohortPin
    from app_module.recommendation_portfolio_calendar_acceptance_binding_v1 import PortfolioCalendarAcceptanceBindingV1


_PORTABLE_KEYS = frozenset(
    {
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "TECHNICAL_UNIVERSE_READ_ROOT",
        "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
        "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
        "MONTHLY_REVENUE_COHORT_BINDING_PATH",
        "MONTHLY_REVENUE_COHORT_BINDING_SHA256",
        "MONTHLY_REVENUE_SERIES_BINDING_PATH",
        "MONTHLY_REVENUE_SERIES_BINDING_SHA256",
        "CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH",
        "CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256",
        "PERSONAL_H20_SQLITE_READ_ROOT",
        "PAPER_CONTRACT_ARTIFACTS_ROOT",
        "RESEARCH_STATE_ROOT",
        "OFFICIAL_CALENDAR_CACHE_PATH",
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
    paper_contract_artifacts_root_error: str | None = None

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
            "paper_contract_artifacts_root_error": self.paper_contract_artifacts_root_error,
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
    paper_key = "PAPER_CONTRACT_ARTIFACTS_ROOT"
    paper_contract_root_error: str | None = None
    paper_value: str | None = None
    if paper_key in source:
        raw_paper_value = source[paper_key]
        if not isinstance(raw_paper_value, str):
            raise ValueError(f"環境變數 {paper_key} 必須是字串")
        paper_value = raw_paper_value.strip()
        json_values.pop(paper_key, None)
        if not paper_value:
            paper_contract_root_error = f"{paper_key} 未設定或為空；Paper 快照查找已停用。"
    elif paper_key in json_values:
        paper_value = json_values.pop(paper_key).strip()
        if not paper_value:
            paper_contract_root_error = f"{paper_key} 未設定或為空；Paper 快照查找已停用。"
    else:
        paper_contract_root_error = f"未提供 {paper_key}；Paper 快照查找已停用。"

    if paper_value:
        paper_candidate = Path(paper_value)
        if not paper_candidate.is_absolute():
            paper_contract_root_error = (
                f"{paper_key} 必須是明示絕對路徑；Paper 快照查找已停用。"
            )
        else:
            blocker = _paper_contract_artifacts_root_path_error(paper_candidate)
            if blocker is not None:
                paper_contract_root_error = blocker
            else:
                environment_values[paper_key] = _normalize_configured_path(
                    paper_key, paper_value
                )

    for key in sorted(_PORTABLE_KEYS - {paper_key}):
        value = _optional_environment_text(source, key)
        if key in {
            "TECHNICAL_UNIVERSE_READ_ROOT",
            "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
            "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
            "MONTHLY_REVENUE_COHORT_BINDING_PATH",
            "MONTHLY_REVENUE_COHORT_BINDING_SHA256",
            "MONTHLY_REVENUE_SERIES_BINDING_PATH",
            "MONTHLY_REVENUE_SERIES_BINDING_SHA256",
            "CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH",
            "CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256",
            "PERSONAL_H20_SQLITE_READ_ROOT",
        } and key in source and value is None:
            if key.endswith("BINDING_SHA256"):
                raise ValueError(f"{key} 必須是非空SHA-256")
            raise ValueError(f"{key} 必須是非空絕對路徑")
        if value is not None:
            _validate_setting(key, value, origin="環境變數")
            environment_values[key] = _normalize_configured_path(key, value)
        elif key in json_values:
            environment_values[key] = json_values[key]

    effective.update(json_values)
    effective.update(environment_values)
    _daily_monthly_cohort_binding_selection(effective)
    _daily_monthly_series_binding_selection(effective)
    _portfolio_calendar_acceptance_binding_selection(effective)
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
        calendar_path = effective.get("OFFICIAL_CALENDAR_CACHE_PATH")
        if calendar_path is not None and any(
            _is_same_or_child(Path(calendar_path), bundle) for bundle in bundle_roots
        ):
            raise ValueError("OFFICIAL_CALENDAR_CACHE_PATH 必須位於 frozen 程式包之外")
        technical_root = effective.get("TECHNICAL_UNIVERSE_READ_ROOT")
        official_root = effective.get("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT")
        if official_root is not None and any(
            _is_same_or_child(Path(official_root), bundle) for bundle in bundle_roots
        ):
            raise ValueError("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT 必須位於 frozen 程式包之外")
        if technical_root is not None and any(
            _is_same_or_child(Path(technical_root), bundle) for bundle in bundle_roots
        ):
            raise ValueError("TECHNICAL_UNIVERSE_READ_ROOT 必須位於 frozen 程式包之外")
        fundamental_root = effective.get("FUNDAMENTAL_READ_SNAPSHOT_ROOT")
        if fundamental_root is not None and any(
            _is_same_or_child(Path(fundamental_root), bundle) for bundle in bundle_roots
        ):
            raise ValueError("FUNDAMENTAL_READ_SNAPSHOT_ROOT 必須位於 frozen 程式包之外")
        monthly_binding = effective.get("MONTHLY_REVENUE_COHORT_BINDING_PATH")
        if monthly_binding is not None and any(
            _is_same_or_child(Path(monthly_binding), bundle) for bundle in bundle_roots
        ):
            raise ValueError("MONTHLY_REVENUE_COHORT_BINDING_PATH 必須位於 frozen 程式包之外")
        series_binding = effective.get("MONTHLY_REVENUE_SERIES_BINDING_PATH")
        if series_binding is not None and any(
            _is_same_or_child(Path(series_binding), bundle) for bundle in bundle_roots
        ):
            raise ValueError("MONTHLY_REVENUE_SERIES_BINDING_PATH 必須位於 frozen 程式包之外")
        calendar_binding = effective.get("CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH")
        if calendar_binding is not None and any(
            _is_same_or_child(Path(calendar_binding), bundle) for bundle in bundle_roots
        ):
            raise ValueError("CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH 必須位於 frozen 程式包之外")
        h20_read_root = effective.get("PERSONAL_H20_SQLITE_READ_ROOT")
        if h20_read_root is not None and any(
            _is_same_or_child(Path(h20_read_root), bundle) for bundle in bundle_roots
        ):
            raise ValueError("PERSONAL_H20_SQLITE_READ_ROOT 必須位於 frozen 程式包之外")
        paper_contract_root = effective.get("PAPER_CONTRACT_ARTIFACTS_ROOT")
        if paper_contract_root is not None and any(
            _is_same_or_child(Path(paper_contract_root), bundle) for bundle in bundle_roots
        ):
            effective.pop("PAPER_CONTRACT_ARTIFACTS_ROOT", None)
            paper_contract_root_error = (
                "PAPER_CONTRACT_ARTIFACTS_ROOT 位於 frozen 程式包內；Paper 快照查找已停用。"
            )
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
        paper_contract_artifacts_root_error=paper_contract_root_error,
    )


def apply_application_settings(settings: ApplicationSettings) -> None:
    """明確套用環境設定並建立外部 runtime 目錄，不接觸資料庫或模型。"""

    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是 ApplicationSettings")
    environment = dict(settings.environment)
    paper_key = "PAPER_CONTRACT_ARTIFACTS_ROOT"
    paper_contract_root_error = settings.paper_contract_artifacts_root_error
    paper_root_value = environment.get(paper_key)
    paper_root: Path | None = None
    if paper_root_value is None:
        if paper_contract_root_error is None:
            paper_contract_root_error = f"未提供 {paper_key}；Paper 快照查找已停用。"
    elif not isinstance(paper_root_value, str):
        raise ValueError("environment 的鍵和值都必須是字串")
    else:
        candidate_paper_root = Path(paper_root_value.strip())
        if not candidate_paper_root.is_absolute():
            paper_contract_root_error = (
                f"{paper_key} 必須是明示絕對路徑；Paper 快照查找已停用。"
            )
        else:
            blocker = _paper_contract_artifacts_root_path_error(candidate_paper_root)
            if blocker is not None:
                paper_contract_root_error = blocker
            else:
                paper_root = _canonical_path(candidate_paper_root)
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ValueError("environment 的鍵和值都必須是字串")
    if "DATA_ROOT" not in environment or "OUTPUT_ROOT" not in environment:
        raise ValueError("environment 必須包含 DATA_ROOT 與 OUTPUT_ROOT")
    monthly_selection = _daily_monthly_cohort_binding_selection(environment)
    series_selection = _daily_monthly_series_binding_selection(environment)
    calendar_selection = _portfolio_calendar_acceptance_binding_selection(environment)

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
    technical_root = environment.get("TECHNICAL_UNIVERSE_READ_ROOT")
    official_root = environment.get("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT")
    official_path = (
        None if official_root is None
        else _absolute_environment_path("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT", official_root)
    )
    technical_path = (
        None if technical_root is None
        else _absolute_environment_path("TECHNICAL_UNIVERSE_READ_ROOT", technical_root)
    )
    fundamental_root = environment.get("FUNDAMENTAL_READ_SNAPSHOT_ROOT")
    fundamental_path = (
        None if fundamental_root is None
        else _absolute_environment_path("FUNDAMENTAL_READ_SNAPSHOT_ROOT", fundamental_root)
    )
    h20_read_root_value = environment.get("PERSONAL_H20_SQLITE_READ_ROOT")
    h20_read_root = (
        None if h20_read_root_value is None
        else _absolute_environment_path("PERSONAL_H20_SQLITE_READ_ROOT", h20_read_root_value)
    )

    if bool(getattr(sys, "frozen", False)):
        bundles = _frozen_bundle_roots(_canonical_path(settings.resource_root))
        if monthly_selection is not None and any(
            _is_same_or_child(Path(monthly_selection[0]), bundle) for bundle in bundles
        ):
            raise ValueError("MONTHLY_REVENUE_COHORT_BINDING_PATH 必須位於 frozen 程式包之外")
        if series_selection is not None and any(
            _is_same_or_child(Path(series_selection[0]), bundle) for bundle in bundles
        ):
            raise ValueError("MONTHLY_REVENUE_SERIES_BINDING_PATH 必須位於 frozen 程式包之外")
        if calendar_selection is not None and any(
            _is_same_or_child(Path(calendar_selection[0]), bundle) for bundle in bundles
        ):
            raise ValueError("CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH 必須位於 frozen 程式包之外")
        if official_path is not None and any(
            _is_same_or_child(official_path, bundle) for bundle in bundles
        ):
            raise ValueError("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT 必須位於 frozen 程式包之外")
        if technical_path is not None:
            if any(_is_same_or_child(technical_path, bundle) for bundle in bundles):
                raise ValueError("TECHNICAL_UNIVERSE_READ_ROOT 必須位於 frozen 程式包之外")
        if fundamental_path is not None and any(
            _is_same_or_child(fundamental_path, bundle) for bundle in bundles
        ):
            raise ValueError("FUNDAMENTAL_READ_SNAPSHOT_ROOT 必須位於 frozen 程式包之外")
        if h20_read_root is not None and any(
            _is_same_or_child(h20_read_root, bundle) for bundle in bundles
        ):
            raise ValueError("PERSONAL_H20_SQLITE_READ_ROOT 必須位於 frozen 程式包之外")
        if paper_root is not None and any(
            _is_same_or_child(paper_root, bundle) for bundle in bundles
        ):
            paper_root = None
            paper_contract_root_error = (
                "PAPER_CONTRACT_ARTIFACTS_ROOT 位於 frozen 程式包內；Paper 快照查找已停用。"
            )
        for name, path in (
            ("DATA_ROOT", data_root),
            ("OUTPUT_ROOT", output_root),
            ("MPLCONFIGDIR", mplconfig_root),
            ("研究 registry 根目錄", registry_root),
        ):
            if any(_is_same_or_child(path, bundle) for bundle in bundles):
                raise ValueError(f"{name} 必須位於 frozen 程式包之外")

    if paper_root is None:
        environment.pop(paper_key, None)
    else:
        environment[paper_key] = str(paper_root)
    for directory in (runtime_root, registry_root, mplconfig_root):
        directory.mkdir(parents=True, exist_ok=True)
    os.environ.update(environment)
    if paper_root is None:
        os.environ.pop(paper_key, None)
        os.environ["_BALDR_PAPER_CONTRACT_ARTIFACTS_ROOT_BLOCKER"] = (
            paper_contract_root_error
            or f"未提供 {paper_key}；Paper 快照查找已停用。"
        )
    else:
        os.environ.pop("_BALDR_PAPER_CONTRACT_ARTIFACTS_ROOT_BLOCKER", None)


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
        if not isinstance(value, str):
            raise ValueError(f"{key} 必須是字串")
        if key == "PAPER_CONTRACT_ARTIFACTS_ROOT":
            values[key] = value.strip()
            continue
        if not value.strip():
            raise ValueError(f"{key} 必須是非空字串")
        _validate_setting(key, value, origin="config.json")
        values[key] = _normalize_configured_path(key, value)
    return values


def _validate_setting(key: str, value: str, *, origin: str) -> None:
    if not value.strip():
        raise ValueError(f"{origin} 的 {key} 必須是非空字串")
    if key.endswith(("ROOT", "PATH", "SOURCE")) and not Path(value).is_absolute():
        raise ValueError(f"{origin} 的 {key} 必須是絕對路徑")
    if key in {"MONTHLY_REVENUE_COHORT_BINDING_SHA256", "MONTHLY_REVENUE_SERIES_BINDING_SHA256", "CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256"} and re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{origin} 的 {key} 必須是64位小寫SHA-256")


def _daily_monthly_cohort_binding_selection(values: Mapping[str, str]) -> tuple[str, str] | None:
    """成對解析明示artifact／外部hash；純設定階段不讀來源。"""
    path_key = "MONTHLY_REVENUE_COHORT_BINDING_PATH"
    hash_key = "MONTHLY_REVENUE_COHORT_BINDING_SHA256"
    if path_key not in values and hash_key not in values:
        return None
    if path_key not in values or hash_key not in values:
        raise ValueError(f"{path_key} 與 {hash_key} 必須一起明示")
    path, digest = values[path_key], values[hash_key]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError("月營收cohort設定必須是字串")
    _validate_setting(path_key, path, origin="設定快照")
    _validate_setting(hash_key, digest, origin="設定快照")
    return path, digest


def _portfolio_calendar_acceptance_binding_selection(values: Mapping[str, str]) -> tuple[str, str] | None:
    """只核caller設定快照；此階段不讀接受或批次。"""
    path_key = "CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH"
    hash_key = "CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256"
    if path_key not in values and hash_key not in values:
        return None
    if path_key not in values or hash_key not in values:
        raise ValueError(f"{path_key} 與 {hash_key} 必須一起明示")
    path, digest = values[path_key], values[hash_key]
    if type(path) is not str or type(digest) is not str:
        raise ValueError("日曆用途接受設定必須是字串")
    _validate_setting(path_key, path, origin="設定快照")
    _validate_setting(hash_key, digest, origin="設定快照")
    return path, digest


def configured_portfolio_calendar_acceptance_binding(
    settings: ApplicationSettings, *, protected_roots: Sequence[Path],
) -> PortfolioCalendarAcceptanceBindingV1 | None:
    """正常Main明示載入外部接受設定；不讀批次、不建立接受或選latest。"""
    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是ApplicationSettings")
    selected = _portfolio_calendar_acceptance_binding_selection(settings.environment)
    if selected is None:
        return None
    from app_module.recommendation_portfolio_calendar_acceptance_binding_v1 import read_portfolio_calendar_acceptance_binding_v1

    forbidden = (
        _frozen_bundle_roots(_canonical_path(settings.resource_root))
        if bool(getattr(sys, "frozen", False)) else ()
    )
    return read_portfolio_calendar_acceptance_binding_v1(
        Path(selected[0]), expected_sha256=selected[1],
        protected_roots=tuple(protected_roots) + forbidden,
    )


def configured_daily_monthly_revenue_cohort_reader(
    settings: ApplicationSettings,
) -> DailyMonthlyRevenueCohortReader | None:
    """正常composition只載入外部設定精確選定的cohort，不接受latest或候選替代。"""
    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是ApplicationSettings")
    selected = _daily_monthly_cohort_binding_selection(settings.environment)
    _daily_monthly_series_binding_selection(settings.environment)
    if selected is None:
        return None
    from data_module.daily_monthly_revenue_cohort_binding import read_daily_monthly_revenue_cohort_binding

    forbidden = (
        _frozen_bundle_roots(_canonical_path(settings.resource_root))
        if bool(getattr(sys, "frozen", False)) else ()
    )
    return read_daily_monthly_revenue_cohort_binding(
        Path(selected[0]), expected_binding_sha256=selected[1], forbidden_roots=forbidden,
    )


def _daily_monthly_series_binding_selection(values: Mapping[str, str]) -> tuple[str, str] | None:
    path_key = "MONTHLY_REVENUE_SERIES_BINDING_PATH"
    hash_key = "MONTHLY_REVENUE_SERIES_BINDING_SHA256"
    if path_key not in values and hash_key not in values:
        return None
    if path_key not in values or hash_key not in values:
        raise ValueError(f"{path_key} 與 {hash_key} 必須一起明示")
    path, digest = values[path_key], values[hash_key]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError("月營收series設定必須是字串")
    _validate_setting(path_key, path, origin="設定快照")
    _validate_setting(hash_key, digest, origin="設定快照")
    if _daily_monthly_cohort_binding_selection(values) is not None:
        raise ValueError("月營收固定cohort與daily series設定不可同時啟用")
    return path, digest


def configured_daily_monthly_revenue_series_reader_factory(
    settings: ApplicationSettings,
) -> Callable[[datetime], DailyMonthlyRevenueCohortReader] | None:
    """凍結設定錨點；每次自然決策首次使用時才讀取系列指標。"""
    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是ApplicationSettings")
    selected = _daily_monthly_series_binding_selection(settings.environment)
    if selected is None:
        return None
    path, digest = selected
    forbidden = (
        _frozen_bundle_roots(_canonical_path(settings.resource_root))
        if bool(getattr(sys, "frozen", False)) else ()
    )

    def select_reader(cutoff_at: datetime) -> DailyMonthlyRevenueCohortReader:
        from data_module.daily_monthly_revenue_series_binding import read_daily_monthly_revenue_series_binding_v1

        selection = read_daily_monthly_revenue_series_binding_v1(
            Path(path), expected_binding_sha256=digest,
            cutoff_at=cutoff_at, forbidden_roots=forbidden,
        )
        selection.verify_integrity()
        return selection.reader

    return select_reader


def configured_daily_monthly_revenue_exact_pin_reader_factory(
    settings: ApplicationSettings,
) -> Callable[[DailyMonthlyRevenueCohortPin, datetime], DailyMonthlyRevenueCohortReader] | None:
    """保存查詢重開只用固定接受與 exact pin，不重新選每日 catalog。"""
    if not isinstance(settings, ApplicationSettings):
        raise TypeError("settings 必須是ApplicationSettings")
    selected = _daily_monthly_series_binding_selection(settings.environment)
    if selected is None:
        return None
    path, digest = selected
    forbidden = (
        _frozen_bundle_roots(_canonical_path(settings.resource_root))
        if bool(getattr(sys, "frozen", False)) else ()
    )

    def exact_reader(pin: DailyMonthlyRevenueCohortPin, cutoff: datetime) -> DailyMonthlyRevenueCohortReader:
        from data_module.daily_monthly_revenue_series_binding import read_daily_monthly_revenue_series_exact_pin_v1

        selection = read_daily_monthly_revenue_series_exact_pin_v1(
            Path(path), expected_binding_sha256=digest, cohort_pin=pin,
            expected_cohort_sha256=pin.cohort_sha256, cutoff_at=cutoff,
            forbidden_roots=forbidden,
        )
        selection.verify_integrity()
        return selection.reader

    return exact_reader


def _normalize_configured_path(key: str, value: str) -> str:
    if key in {"MONTHLY_REVENUE_COHORT_BINDING_PATH", "MONTHLY_REVENUE_SERIES_BINDING_PATH", "CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH"}:
        # 保留caller明示的路徑，loader仍須看見並拒絕symlink／reparse alias。
        return str(Path(value))
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
