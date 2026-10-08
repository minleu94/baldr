"""選擇個人 Watchlist 儲存並保留既有 typed service API。

Personal mode is opt-in through a complete pair of config values. Construction
is read-only: it never creates the personal root, a database, or a legacy file.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from app_module.personal_data_paths import (
    PersonalDataPathError,
    PersonalDataPaths,
    WatchlistCowControlPaths,
    resolve_personal_data_paths,
)
from app_module.watchlist_cow_activation import (
    activate_watchlist_sqlite,
    preview_watchlist_sqlite_activation,
    resolve_watchlist_sqlite_activation,
    rollback_watchlist_sqlite,
    watchlist_service_writer_guard,
)
from app_module.watchlist_service import WatchlistService, WatchlistStorageStatus
from data_module.watchlist_json_cow import (
    convert_watchlist_json,
    dry_run_watchlist_json,
)
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_sqlite_cow import (
    convert_watchlist_sqlite,
    dry_run_watchlist_sqlite,
)


_SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


class PersonalWatchlistSelectionError(RuntimeError):
    """Personal selector 或明示升級遇到 fail-closed 條件。"""


def _configured(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def build_watchlist_service(config: Any) -> WatchlistService:
    """Return the legacy service by default, or the explicit personal adapter.

    The two personal settings form one selector. A partial pair is a setup
    error, never a reason to silently use the market output writer.
    """

    personal_root = getattr(config, "personal_data_root", None)
    source_path = getattr(config, "personal_watchlist_source", None)
    root_set = _configured(personal_root)
    source_set = _configured(source_path)
    if not root_set and not source_set:
        repository, storage_status = WatchlistService.discover_repository(config)
        return WatchlistService(
            config,
            repository=repository,
            storage_status=storage_status,
        )
    if root_set != source_set:
        raise PersonalWatchlistSelectionError(
            "personal_data_root and personal_watchlist_source must be configured together"
        )
    return PersonalWatchlistService(config)


class PersonalWatchlistService(WatchlistService):
    """A WatchlistService adapter whose only writer is the active personal DB."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self._local_writer_lock = RLock()
        market_root = getattr(config, "data_root", None)
        if market_root is None:
            raise PersonalWatchlistSelectionError("personal mode requires config.data_root")
        output_root = getattr(config, "output_root", None)
        if output_root is None:
            output_root = Path(market_root) / "output"
        try:
            self.personal_paths: PersonalDataPaths = resolve_personal_data_paths(
                market_root,
                personal_root=getattr(config, "personal_data_root"),
                legacy_output_root=output_root,
                environ={},
            )
            package_root = Path(__file__).resolve().parents[1]
            if (
                self.personal_paths.personal_root == package_root
                or self.personal_paths.personal_root.is_relative_to(package_root)
                or package_root.is_relative_to(self.personal_paths.personal_root)
            ):
                raise PersonalDataPathError(
                    "personal_root_overlaps_application_package",
                    self.personal_paths.personal_root,
                )
            self.control_paths = WatchlistCowControlPaths(
                self.personal_paths,
                Path(getattr(config, "personal_watchlist_source")).expanduser(),
            )
        except (PersonalDataPathError, TypeError, ValueError) as exc:
            raise PersonalWatchlistSelectionError(str(exc)) from exc

        # These fields are consumed by WatchlistService's typed JSON/repository
        # adapter methods. Avoid its initializer: it creates OUTPUT_ROOT files.
        self.watchlist_dir = self.personal_paths.watchlist_db.parent
        self.default_watchlist_file = self.control_paths.source_path
        self.canonical_repository_path = self.personal_paths.watchlist_db
        self.repository: WatchlistRepository | None = None
        self._source_read_allowed = False
        self._storage_status = self._discover_personal_storage()

    def personal_storage_preview(self) -> dict[str, str]:
        """Return a path-only preview without creating any directories."""

        return {
            "source": str(self.control_paths.source_path),
            "target": str(self.personal_paths.watchlist_db),
            "marker": str(self.control_paths.marker_path),
            "receipt": str(self.control_paths.receipt_path),
            "backup": str(self.control_paths.source_backup_path),
            "rollback_audit_root": str(self.personal_paths.marker_backup_root),
            "status": self._storage_status.mode,
            "upgrade_available": str(self._storage_status.upgrade_available).lower(),
        }

    def _status(
        self,
        mode: str,
        *,
        upgrade_available: bool = False,
        message: str,
        marker_sha256: str | None = None,
        source_path: Path | None = None,
    ) -> WatchlistStorageStatus:
        return WatchlistStorageStatus(
            mode=mode,
            repository_path=self.personal_paths.watchlist_db,
            legacy_path=self.control_paths.source_path,
            upgrade_available=upgrade_available,
            message=message,
            activation_marker_sha256=marker_sha256,
            activation_source_path=source_path,
        )

    def _set_source_read_model(self) -> tuple[WatchlistRepository | None, bool, str]:
        """Select a read-only view of the configured legacy source."""

        source = self.control_paths.source_path
        try:
            # Revalidate before opening any source. It rejects links, hardlinks,
            # path escapes and personal-control aliases without creating files.
            self.control_paths.validate(source, self.personal_paths.watchlist_db)
        except (PersonalDataPathError, OSError, ValueError) as exc:
            self._source_read_allowed = False
            return None, False, f"個人來源路徑驗證失敗；不讀取來源。 {exc}"
        if not source.is_file():
            self._source_read_allowed = False
            return None, False, "個人模式來源不存在；writer 已封鎖。"
        suffix = source.suffix.casefold()
        if suffix == ".json":
            self._source_read_allowed = True
            return None, True, "個人 DB 尚未啟用；目前只讀 legacy JSON，明示升級前不接受保存。"
        if suffix not in _SQLITE_SUFFIXES:
            self._source_read_allowed = False
            return None, False, "個人模式來源副檔名不受支援；writer 已封鎖。"
        repository = WatchlistRepository(source)
        storage = repository.detect_storage_format()
        if storage.get("schema_version") in {1, 2} and storage.get("ready") is True:
            self._source_read_allowed = True
            return repository, True, "SQLite v1/v2 來源僅供唯讀；可明示升級至個人 SQLite v3。"
        if storage.get("schema_version") == 3 and storage.get("ready") is True:
            self._source_read_allowed = True
            return repository, False, "來源為 SQLite v3，但不是已啟用的個人目標；僅供唯讀。"
        self._source_read_allowed = False
        return None, False, "個人模式 SQLite 來源 schema 無法辨識；writer 已封鎖。"

    def _discover_personal_storage(self) -> WatchlistStorageStatus:
        """Resolve personal COW state without initializing files or directories."""

        source = self.control_paths.source_path
        target = self.personal_paths.watchlist_db
        marker = self.control_paths.marker_path
        receipt = self.control_paths.receipt_path

        # Any explicit pointer, including a dangling link, suppresses fallback.
        if marker.exists() or marker.is_symlink():
            resolved = resolve_watchlist_sqlite_activation(source, control_paths=self.control_paths)
            state = str(resolved.get("status", "blocked"))
            marker_sha = str(resolved.get("marker_sha256", "")) or None
            if state == "active":
                selected = Path(str(resolved.get("repository_path", "")))
                if selected != target:
                    self.repository = None
                    return self._status(
                        "blocked",
                        message="個人 activation target 不符；writer 已封鎖。",
                        marker_sha256=marker_sha,
                        source_path=source,
                    )
                self.repository = WatchlistRepository(selected)
                return self._status(
                    "repository",
                    message="個人 SQLite v3 已啟用；讀寫固定使用 personal root。",
                    marker_sha256=marker_sha,
                    source_path=source,
                )
            readonly_repo, _, source_message = self._set_source_read_model()
            self.repository = readonly_repo
            if state == "rolled_back":
                mode = "personal_rolled_back_readonly"
                message = "個人 COW 已回退；舊來源僅供唯讀，個人 writer 已停止。"
            else:
                mode = "blocked"
                message = f"個人 activation 狀態無效；writer 已封鎖。 {resolved.get('code', '')}"
            return self._status(
                mode,
                message=f"{message} {source_message}",
                marker_sha256=marker_sha,
                source_path=source,
            )

        # A target/receipt without its durable marker is an interrupted or
        # ambiguous conversion. Keep both source and target intact and stop.
        if any(path.exists() or path.is_symlink() for path in (target, receipt)):
            readonly_repo, _, source_message = self._set_source_read_model()
            self.repository = readonly_repo
            return self._status(
                "blocked",
                message=f"找到未啟用的 personal target／receipt；writer 已封鎖。 {source_message}",
                source_path=source,
            )

        try:
            # Validates source scope, hardlink/link status, and personal paths;
            # this call is read-only and creates no directories.
            self.control_paths.validate(source, target)
        except (PersonalDataPathError, OSError, ValueError) as exc:
            self.repository = None
            return self._status(
                "blocked",
                message=f"個人來源路徑驗證失敗；writer 已封鎖。 {exc}",
                source_path=source,
            )

        readonly_repo, upgrade_available, source_message = self._set_source_read_model()
        self.repository = readonly_repo
        if source_message.startswith("個人模式來源不存在"):
            mode = "blocked"
        elif readonly_repo is not None:
            mode = "repository_readonly"
        else:
            mode = "personal_source_readonly"
        return self._status(
            mode,
            upgrade_available=upgrade_available,
            message=source_message,
            source_path=source,
        )

    def _require_active_writer(self) -> None:
        if self._storage_status.mode != "repository" or self.repository is None:
            raise PersonalWatchlistSelectionError(
                "personal_watchlist_readonly: 明示升級並啟用個人儲存前不可保存"
            )

    def _review_writer_allowed(self) -> bool:
        return self._storage_status.mode == "repository" and self.repository is not None

    def _require_review_writer(self) -> None:
        self._require_active_writer()

    @contextmanager
    def _writer_guard(self) -> Iterator[None]:
        # 同一實例的背景讀取先排隊；外部與巢狀操作仍須通過原 marker 守衛。
        with self._local_writer_lock:
            self._require_active_writer()
            assert self.repository is not None
            with watchlist_service_writer_guard(
                self.canonical_repository_path,
                expected_marker_sha256=self._storage_status.activation_marker_sha256,
                activation_source_path=self.control_paths.source_path,
                expected_target_path=self.repository.db_path,
                control_paths=self.control_paths,
            ):
                yield

    def _load_watchlist(self, watchlist_id: str):
        if self._storage_status.mode == "repository":
            with self._writer_guard():
                return super()._load_watchlist(watchlist_id)
        if not self._source_read_allowed:
            raise PersonalWatchlistSelectionError(
                "personal_watchlist_source_unavailable: 不讀取未通過路徑驗證的來源"
            )
        try:
            self.control_paths.validate(
                self.control_paths.source_path,
                self.personal_paths.watchlist_db,
            )
        except (PersonalDataPathError, OSError, ValueError) as exc:
            self._source_read_allowed = False
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_source_unavailable: {exc}"
            ) from exc
        return super()._load_watchlist(watchlist_id)

    def upgrade_to_repository(self) -> WatchlistStorageStatus:
        """Explicitly convert, preview, activate, then rediscover the pointer."""

        if self._storage_status.mode == "repository":
            return self._storage_status
        if not self._storage_status.upgrade_available:
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_upgrade_unavailable: {self._storage_status.message}"
            )
        source = self.control_paths.source_path
        target = self.personal_paths.watchlist_db
        if self.control_paths.marker_path.exists() or self.control_paths.marker_path.is_symlink():
            raise PersonalWatchlistSelectionError("personal activation marker already exists")
        if target.exists() or target.is_symlink() or self.control_paths.receipt_path.exists():
            raise PersonalWatchlistSelectionError("personal target or receipt already exists")

        suffix = source.suffix.casefold()
        if suffix == ".json":
            dry_run = dry_run_watchlist_json(source, target, control_paths=self.control_paths)
            if dry_run.get("status") != "dry_run":
                raise PersonalWatchlistSelectionError(
                    f"personal_watchlist_dry_run_blocked: {dry_run.get('error_code', 'unknown')}"
                )
            converted = convert_watchlist_json(source, target, control_paths=self.control_paths)
        elif suffix in _SQLITE_SUFFIXES:
            dry_run = dry_run_watchlist_sqlite(source, target, control_paths=self.control_paths)
            if dry_run.get("status") != "dry_run":
                raise PersonalWatchlistSelectionError(
                    f"personal_watchlist_dry_run_blocked: {dry_run.get('error_code', 'unknown')}"
                )
            converted = convert_watchlist_sqlite(source, target, control_paths=self.control_paths)
        else:
            raise PersonalWatchlistSelectionError("personal_watchlist_source_format_unsupported")

        if converted.get("status") != "ready":
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_convert_blocked: {converted.get('error_code', 'unknown')}"
            )
        preview = preview_watchlist_sqlite_activation(
            source, target, control_paths=self.control_paths,
        )
        if preview.get("status") != "ready":
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_activation_preview_blocked: {preview.get('code', preview.get('status', 'unknown'))}"
            )
        activated = activate_watchlist_sqlite(
            source, target, control_paths=self.control_paths,
        )
        if activated.get("status") not in {"activated", "already_active"}:
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_activation_failed: {activated.get('code', activated.get('status', 'unknown'))}"
            )

        self._storage_status = self._discover_personal_storage()
        if self._storage_status.mode != "repository":
            raise PersonalWatchlistSelectionError(
                f"personal_watchlist_fresh_discovery_failed: {self._storage_status.message}"
            )
        return self._storage_status

    def rollback_to_source(self) -> dict[str, Any]:
        """Explicitly stop the personal writer and retain its database/history."""

        self._require_active_writer()
        result = rollback_watchlist_sqlite(
            self.control_paths.source_path,
            control_paths=self.control_paths,
        )
        self._storage_status = self._discover_personal_storage()
        return result


__all__ = [
    "PersonalWatchlistSelectionError",
    "PersonalWatchlistService",
    "build_watchlist_service",
]
