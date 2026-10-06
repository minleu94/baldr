"""由明示 Paper route 映射既有檔名；不建立、搬移或補造資料。"""

from dataclasses import dataclass
from pathlib import Path
import os
import stat
from contextlib import contextmanager
import sqlite3
from typing import Iterator
from app_module.personal_data_paths import PersonalDataPaths, PersonalDataPathError, _absolute, to_internal_io_path, to_internal_sqlite_uri
from app_module.personal_store_selection import assert_personal_store_path
from app_module.sqlite_read_only import configure_read_only_connection

from app_module.personal_store_routes import (
    PersonalStoreDomain, PersonalStoreMode, PersonalStoreRoute, PersonalStoreRouteError,
)


class PersonalStoreCustody:
    """每次 I/O 驗證 caller 的 canonical path；不建立檔案或資料夾。"""

    def __init__(self, route: PersonalStoreRoute | None, paths: PersonalDataPaths | None):
        self.route = route
        self.paths = paths
        self._allowed: set[Path] = set()
        if route is not None:
            selected = {route.read_source}
            if route.domain is PersonalStoreDomain.PAPER:
                pp = PersonalPaperStorePaths.from_route(route, portfolio_id=route.identity.key)
                selected.update((pp.state_db, pp.benchmark_db, pp.baseline, pp.status))
            for value in selected:
                self._allowed.add(value)
                self._allowed.add(value.with_name(f".{value.name}.lock"))
                for suffix in ("-journal", "-wal", "-shm"):
                    self._allowed.add(value.with_name(value.name + suffix))
            if route.mode is PersonalStoreMode.PERSONAL and paths is None:
                raise PersonalStoreRouteError("personal_paths_required")
            self.guard(route.read_source)

    def guard(self, path: Path) -> Path:
        if self.route is None:
            return path
        if path not in self._allowed:
            raise PersonalStoreRouteError("personal_store_selected_path_mismatch", str(path))
        if self.route.mode is PersonalStoreMode.PERSONAL:
            if self.paths is None:
                raise PersonalStoreRouteError("personal_paths_required")
            return assert_personal_store_path(self.paths, path)
        canonical = _absolute(path)
        if canonical != path:
            raise PersonalDataPathError("personal_store_path_alias", path)
        try:
            info = os.stat(to_internal_io_path(canonical), follow_symlinks=False)
        except FileNotFoundError:
            return canonical
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PersonalDataPathError("personal_store_alias_or_type", canonical)
        return canonical

    def io(self, path: Path) -> str:
        canonical = self.guard(path)
        return str(canonical) if self.route is None else to_internal_io_path(canonical)

    def exists(self, path: Path) -> bool:
        return os.path.isfile(self.io(path))

    def prepare_parent(self, path: Path) -> None:
        Path(self.io(path)).parent.mkdir(parents=True, exist_ok=True)
        self.guard(path)

    def sqlite_guard(self, path: Path) -> Path:
        canonical = self.guard(path)
        for suffix in ("-journal", "-wal", "-shm"):
            self.guard(path.with_name(path.name + suffix))
        return canonical

    @contextmanager
    def read_sqlite(self, path: Path) -> Iterator[sqlite3.Connection]:
        canonical = self.sqlite_guard(path)
        conn = sqlite3.connect(to_internal_sqlite_uri(canonical, "ro"), uri=True)
        conn.row_factory = sqlite3.Row
        try:
            configure_read_only_connection(conn)
            yield conn
        finally:
            conn.close()


@dataclass(frozen=True)
class PersonalPaperStorePaths:
    state_db: Path
    benchmark_db: Path
    cost_ledger_db: Path
    baseline: Path
    status: Path

    @classmethod
    def from_route(cls, route: PersonalStoreRoute, *, portfolio_id: str) -> "PersonalPaperStorePaths":
        if route.domain is not PersonalStoreDomain.PAPER:
            raise PersonalStoreRouteError("paper_domain_required")
        if not portfolio_id.strip() or route.identity.key != portfolio_id:
            raise PersonalStoreRouteError("paper_identity_mismatch")
        source = route.read_source
        if not source.is_absolute() or ".." in source.parts:
            raise PersonalStoreRouteError("absolute_path_required")
        if source.name != "paper_trade_ledger.sqlite" or source.parent.name != "paper_portfolio":
            raise PersonalStoreRouteError("paper_existing_layout_required")
        root = source.parent.parent
        return cls(
            state_db=source.parent / "paper_portfolio.sqlite",
            benchmark_db=source.parent / "paper_equal_weight_benchmark.sqlite",
            cost_ledger_db=source,
            baseline=source.parent / "baseline_20260712.json",
            status=root / "scheduled" / "paper_portfolio_daily" / "latest_status.json",
        )

    @staticmethod
    def require_selected(override: str | Path | None, selected: Path) -> Path:
        if override is not None and Path(override) != selected:
            raise PersonalStoreRouteError("paper_route_override_mismatch", str(override))
        return selected
