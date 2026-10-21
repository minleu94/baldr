"""個人 notes 的明示 JSONL 路徑與 adapter；不遷移或初始化其他 store。"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app_module.personal_data_paths import (
    PersonalDataPaths, PersonalDataPathError, _absolute, resolve_personal_data_paths,
)
from app_module.portfolio_store import PortfolioJsonlStore, _journal_history_token, project_journal_records
from app_module.dtos.decision_continuity_dtos import DECISION_CONTINUITY_RECORD_TYPE
from app_module.sqlite_read_only import check_read_cancelled


@dataclass(frozen=True)
class JournalStorageSelection:
    """所有 notes caller 共用的選擇；None 明確代表既有相容行為。"""
    paths: PersonalJournalPaths | None = None
    legacy_read_only: bool = False


def resolve_journal_storage_selection(config: Any) -> JournalStorageSelection:
    root = getattr(config, "personal_journal_root", None)
    mode = getattr(config, "personal_journal_mode", None)
    if root is None and mode is None:
        return JournalStorageSelection()
    if root is None or mode is None:
        raise ValueError("personal_journal_selection_incomplete")
    if mode not in ("personal", "legacy_read_only"):
        raise ValueError("personal_journal_mode_invalid")
    paths = resolve_personal_journal_paths(
        config.data_root, personal_root=root, legacy_output_root=config.output_root,
    )
    package_root = Path(__file__).resolve().parents[1]
    personal_root = paths.personal_paths.personal_root
    if personal_root.is_relative_to(package_root) or package_root.is_relative_to(personal_root):
        raise ValueError("personal_root_overlaps_application_package")
    return JournalStorageSelection(paths, mode == "legacy_read_only")


def validate_personal_journal_record(record: Mapping[str, Any]) -> None:
    """未知新版 record type 不降級解讀為 legacy note。"""
    check_read_cancelled()
    if record.get("record_type") not in (None, "", "journal_entry", DECISION_CONTINUITY_RECORD_TYPE):
        raise ValueError("personal_journal_unknown_record_type")


@dataclass(frozen=True)
class PersonalJournalPaths:
    """獨立於 watchlist 啟用的 notes 選擇；建構與 discovery 不 mkdir。"""
    personal_paths: PersonalDataPaths

    @property
    def journal_file(self) -> Path:
        return self.personal_paths.research_notes_root / "journal_entries.jsonl"

    @property
    def lock_file(self) -> Path:
        return self.journal_file.with_name("." + self.journal_file.name + ".lock")

    @property
    def legacy_source(self) -> Path:
        return self.personal_paths.legacy_output_root / "portfolio" / "journal_entries.jsonl"

    @property
    def backup_root(self) -> Path:
        return self.personal_paths.personal_root / "backups" / "research_notes"

    @property
    def audit_root(self) -> Path:
        return self.personal_paths.research_notes_root / "audit"

    @staticmethod
    def _regular(path: Path) -> Path:
        value = _absolute(path)
        try:
            info = value.lstat()
        except FileNotFoundError:
            return value
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PersonalDataPathError("journal_file_alias_or_type", value)
        return value

    def validate(self) -> None:
        self.personal_paths.validate()
        for path in (self.journal_file, self.lock_file):
            value = self._regular(path)
            if not value.is_relative_to(self.personal_paths.personal_root):
                raise PersonalDataPathError("personal_path_escape", value)
        for path in (self.backup_root, self.audit_root):
            value = _absolute(path)
            if not value.is_relative_to(self.personal_paths.personal_root):
                raise PersonalDataPathError("personal_path_escape", value)
            if value.exists() and not value.is_dir():
                raise PersonalDataPathError("directory_root_required", value)

    def read_path(self, *, legacy_read_only: bool = False) -> Path:
        check_read_cancelled()
        self.validate()
        return self._regular(self.legacy_source if legacy_read_only else self.journal_file)

    def assert_selected(self, path: Path, *, legacy_read_only: bool = False) -> None:
        expected = self.read_path(legacy_read_only=legacy_read_only)
        if self._regular(path) != expected:
            raise PersonalDataPathError("journal_path_mismatch", path)


def resolve_personal_journal_paths(market_root: str | Path, *, personal_root: str | Path,
                                   legacy_output_root: str | Path | None = None) -> PersonalJournalPaths:
    """明示 root，忽略全域 watchlist selector；沒有自動 fallback。"""
    result = PersonalJournalPaths(resolve_personal_data_paths(
        market_root, personal_root=personal_root, legacy_output_root=legacy_output_root, environ={},
    ))
    result.validate()
    return result


class PersonalJournalJsonlStore(PortfolioJsonlStore):
    """沿用 append／CAS／sibling OS lock；禁止交易與 overwrite API。

    personal writer 不 mkdir 直到首次操作；legacy 模式完全唯讀，不建 lock。
    路徑檢查不是惡意程序併發換 junction 的 handle-based 防禦；caller 必須
    控制 root 的 writer custody。cancel_check 僅在操作開始檢查，成功 append
    不以 cancellation 倒寫／刪除歷史。backup／audit 僅保留路徑，沒有 producer。
    """
    def __init__(self, paths: PersonalJournalPaths, *, legacy_read_only: bool = False,
                 cancel_check: Callable[[], bool] | None = None) -> None:
        self.paths = paths
        self.legacy_read_only = legacy_read_only
        self.cancel_check = cancel_check
        self.journal_file = paths.read_path(legacy_read_only=legacy_read_only)
        # 不呼叫會建立 portfolio／journal 目錄的父類 constructor。

    def _guard(self, *, write: bool = False) -> None:
        if self.cancel_check is not None and self.cancel_check():
            raise RuntimeError("personal_journal_cancelled")
        self.paths.assert_selected(self.journal_file, legacy_read_only=self.legacy_read_only)
        if write and self.legacy_read_only:
            raise RuntimeError("legacy_journal_read_only")

    def _read_jsonl_unlocked(self, path: Path) -> list[dict[str, Any]]:  # type: ignore[override]
        self.paths.assert_selected(path, legacy_read_only=self.legacy_read_only)
        records = PortfolioJsonlStore._read_jsonl_unlocked(path)
        for record in records:
            validate_personal_journal_record(record)
        return records

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        self._guard()
        self.paths.assert_selected(path, legacy_read_only=self.legacy_read_only)
        if self.legacy_read_only:
            return self._read_legacy()
        if not path.exists():
            return []
        return super()._read_jsonl(path)

    def _ensure_line_separator_unlocked(self, path: Path) -> None:  # type: ignore[override]
        if self.legacy_read_only:
            raise RuntimeError("legacy_journal_read_only")
        self.paths.assert_selected(path)
        PortfolioJsonlStore._ensure_line_separator_unlocked(path)

    def _append_jsonl(self, path: Path, item: dict[str, Any]) -> None:
        self._guard(write=True)
        self.paths.assert_selected(path)
        validate_personal_journal_record(item)
        super()._append_jsonl(path, item)

    def append_journal_revisions(self, revisions: Iterable[Mapping[str, Any]], *,
                                 expected_history_token: str | None = None) -> None:
        self._guard(write=True)
        super().append_journal_revisions(revisions, expected_history_token=expected_history_token)

    def _read_legacy(self) -> list[dict[str, Any]]:
        self._guard()

        def content_identity() -> tuple[int, ...] | None:
            if not self.journal_file.exists():
                return None
            info = self.journal_file.stat()
            # 讀取本身可更新存取時間；檔案身分、內容與其他穩定 metadata 仍須一致。
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                    info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

        before = content_identity()
        result = self._read_jsonl_unlocked(self.journal_file)
        self.paths.assert_selected(self.journal_file, legacy_read_only=True)
        after = content_identity()
        if before != after:
            raise RuntimeError("legacy_journal_changed_during_read")
        return result

    def load_journal_history(self) -> list[dict[str, Any]]:
        self._guard()
        if not self.legacy_read_only and not self.journal_file.exists():
            return []
        return self._read_legacy() if self.legacy_read_only else super().load_journal_history()

    def load_journal_entries(self) -> list[dict[str, Any]]:
        self._guard()
        if not self.legacy_read_only and not self.journal_file.exists():
            return []
        return project_journal_records(self._read_legacy()) if self.legacy_read_only else super().load_journal_entries()

    def load_journal_snapshot(self) -> tuple[list[dict[str, Any]], str]:
        self._guard()
        if not self.legacy_read_only:
            if not self.journal_file.exists():
                return [], _journal_history_token([])
            return super().load_journal_snapshot()
        records = self._read_legacy()
        return records, _journal_history_token(records)

    def append_trade(self, trade: dict[str, Any]) -> None:
        raise RuntimeError("personal_journal_trade_api_disabled")

    def load_trades(self) -> list[dict[str, Any]]:
        raise RuntimeError("personal_journal_trade_api_disabled")

    def overwrite_trades(self, trades: list[dict[str, Any]]) -> None:
        raise RuntimeError("personal_journal_trade_api_disabled")

    def _overwrite_jsonl(self, path: Path, entries: Iterable[Mapping[str, Any]]) -> None:
        raise RuntimeError("personal_journal_append_only")
