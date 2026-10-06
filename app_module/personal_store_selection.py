"""私人 store 的明示配置選擇；不初始化 store、不遷移、不修改全域市場路徑。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat
from typing import Any

from app_module.personal_data_paths import (
    PersonalDataPaths, PersonalDataPathError, _absolute,
    resolve_personal_data_paths, to_internal_io_path,
)
from app_module.personal_store_routes import (
    PersonalStoreDomain, PersonalStoreMode, PersonalStoreRoute,
    PersonalStoreRouteError, StoreIdentity, select_personal_store_route,
)


@dataclass(frozen=True)
class PersonalStoreSelection:
    mode: PersonalStoreMode
    paths: PersonalDataPaths | None
    legacy_output_root: Path
    market_db_path: Path

    def route(
        self, domain: PersonalStoreDomain, identity: StoreIdentity,
        *, portfolio_ledger_path: Path | None = None,
    ) -> PersonalStoreRoute:
        return select_personal_store_route(
            domain=domain, mode=(PersonalStoreMode.MARKET_READ_ONLY
                                if domain is PersonalStoreDomain.EVIDENCE else self.mode),
            identity=identity, personal_paths=self.paths,
            legacy_output_root=self.legacy_output_root, market_db_path=self.market_db_path,
            portfolio_ledger_path=portfolio_ledger_path,
        )


def resolve_personal_store_selection(config: Any) -> PersonalStoreSelection:
    """root/mode 成對 opt-in，與 watchlist／notes 選擇獨立。"""
    root = getattr(config, "personal_store_root", None)
    raw_mode = getattr(config, "personal_store_mode", None)
    output = Path(config.output_root)
    market = Path(getattr(config, "db_file", Path(config.data_root) / "sqlite" / "twstock.db"))
    if root is None and raw_mode is None:
        return PersonalStoreSelection(PersonalStoreMode.LEGACY_COMPAT, None, output, market)
    if root is None or raw_mode is None:
        raise PersonalStoreRouteError("personal_store_selection_incomplete")
    if raw_mode not in (PersonalStoreMode.PERSONAL.value, PersonalStoreMode.LEGACY_READ_ONLY.value):
        raise PersonalStoreRouteError("personal_store_mode_invalid")
    paths = resolve_personal_data_paths(
        config.data_root, personal_root=root, legacy_output_root=output, environ={},
    )
    package = Path(__file__).resolve().parents[1]
    if paths.personal_root.is_relative_to(package) or package.is_relative_to(paths.personal_root):
        raise PersonalStoreRouteError("personal_root_overlaps_application_package")
    return PersonalStoreSelection(PersonalStoreMode(raw_mode), paths, output, market)


def assert_personal_store_path(paths: PersonalDataPaths, path: Path) -> Path:
    """每次 I/O 前驗 canonical、containment、links 與既存 regular-file identity。"""
    paths.validate()
    canonical = _absolute(path)
    if canonical != path or not canonical.is_relative_to(paths.personal_root) or canonical == paths.personal_root:
        raise PersonalDataPathError("personal_store_path_outside_root", path)
    try:
        info = os.stat(to_internal_io_path(canonical), follow_symlinks=False)
    except FileNotFoundError:
        return canonical
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PersonalDataPathError("personal_store_alias_or_type", canonical)
    return canonical
