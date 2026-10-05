"""個人儲存與市場包的唯讀路徑契約；不建立目錄、不遷移或啟用 writer。"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


class PersonalDataPathError(ValueError):
    """可供 caller 顯示的具名路徑拒絕。"""

    def __init__(self, code: str, path: str | Path = "") -> None:
        self.code = code
        super().__init__(f"{code}: {path}")


def _reject_links(path: Path) -> None:
    # lstat 保留 link 身分；Windows reparse 包含 junction，不僅 symlink。
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PersonalDataPathError("path_unavailable", component) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PersonalDataPathError("linked_path", component)


def _absolute(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute() or ".." in value.parts:
        raise PersonalDataPathError("absolute_path_required", value)
    if os.name == "nt":
        if str(value).startswith(("\\\\?\\", "\\\\.\\")):
            raise PersonalDataPathError("ambiguous_windows_path", value)
        # 禁止 ADS、尾端正規化別名與裝置名稱，避免白名單比對與 OS 實際開啟不同。
        for part in value.parts[1:]:
            if ":" in part or part.endswith((" ", ".")) or Path(part).is_reserved():
                raise PersonalDataPathError("ambiguous_windows_path", value)
    _reject_links(value)
    try:
        return value.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PersonalDataPathError("path_unavailable", value) from exc


def _directory(path: Path) -> Path:
    value = _absolute(path)
    if value.exists() and not value.is_dir():
        raise PersonalDataPathError("directory_root_required", value)
    return value


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _separate(left: Path, right: Path) -> None:
    if _overlap(left, right):
        raise PersonalDataPathError("overlapping_roots", f"{left} / {right}")


@dataclass(frozen=True)
class PersonalDataPaths:
    """由明示 root 解析的計畫值；本物件不代表正式位置已獲批准。"""

    market_root: Path
    legacy_output_root: Path
    personal_root: Path

    @property
    def watchlist_db(self) -> Path:
        return self.personal_root / "watchlists" / "watchlists.v3.sqlite"

    @property
    def activation_marker(self) -> Path:
        return self.personal_root / "watchlists" / "watchlists.v3.sqlite.cow-active.json"

    @property
    def conversion_receipt(self) -> Path:
        return self.watchlist_db.with_name(self.watchlist_db.name + ".cow-conversion.v1.json")

    @property
    def backup_root(self) -> Path:
        return self.personal_root / "backups" / "watchlists"

    @property
    def marker_backup_root(self) -> Path:
        return self.personal_root / "activation_backups" / "watchlists"

    @property
    def research_notes_root(self) -> Path:
        return self.personal_root / "research_notes"

    @property
    def ledger_root(self) -> Path:
        return self.personal_root / "ledgers"

    def validate(self) -> None:
        market = _directory(self.market_root)
        output = _directory(self.legacy_output_root)
        personal = _directory(self.personal_root)
        _separate(market, personal)
        _separate(output, personal)
        # 個人子路徑未建立也檢查既有祖先，阻擋日後新增的 link 逃逸。
        for child in (self.watchlist_db, self.activation_marker, self.conversion_receipt,
                      self.backup_root, self.marker_backup_root,
                      self.research_notes_root, self.ledger_root):
            if not _absolute(child).is_relative_to(personal):
                raise PersonalDataPathError("personal_path_escape", child)
            try:
                info = child.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise PersonalDataPathError("path_unavailable", child) from exc
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise PersonalDataPathError("hardlinked_personal_file", child)


def resolve_personal_data_paths(
    market_root: str | Path,
    *,
    personal_root: str | Path | None = None,
    legacy_output_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> PersonalDataPaths:
    """明示參數優先於 PERSONAL_DATA_ROOT；未設定時拒絕，無隱性預設啟用。"""
    env = os.environ if environ is None else environ
    selected = personal_root if personal_root is not None else env.get("PERSONAL_DATA_ROOT", "")
    if not str(selected).strip():
        raise PersonalDataPathError("personal_root_unconfigured")
    market = _absolute(market_root)
    output = _absolute(legacy_output_root if legacy_output_root is not None else market / "output")
    paths = PersonalDataPaths(market, output, _absolute(selected))
    paths.validate()
    return paths


# 只允許既有市場 CSV 類別；output、個人狀態、日誌、任意 JSON／SQLite 均未授權。
_MARKET_CSV_TREES = frozenset({"daily_price", "daily_price_tpex", "technical_analysis", "broker_flow"})
_MARKET_METADATA_FILES = frozenset({
    "market_index.csv", "industry_index.csv", "stock_data_whole.csv",
    "all_stocks_data.csv", "broker_branch_registry.csv",
})


def _market_relative(raw: str) -> Path:
    value = PurePosixPath(raw)
    if not raw or "\\" in raw or ":" in raw or value.is_absolute() or any(
        part in {"", ".", ".."} for part in raw.split("/")
    ):
        raise PersonalDataPathError("invalid_export_relative_path", raw)
    parts = value.parts
    if len(parts) == 2 and parts[0] == "meta_data" and parts[1] in _MARKET_METADATA_FILES:
        return Path(*parts)
    if len(parts) >= 2 and parts[0] in _MARKET_CSV_TREES and value.suffix == ".csv":
        return Path(*parts)
    raise PersonalDataPathError("market_export_not_allowlisted", raw)


@dataclass(frozen=True)
class MarketExportFile:
    relative_path: str
    source_path: Path
    identity: tuple[int, int, int, int, int]


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    _reject_links(path)
    try:
        info = path.stat()
    except OSError as exc:
        raise PersonalDataPathError("export_file_unavailable", path) from exc
    if not stat.S_ISREG(info.st_mode):
        raise PersonalDataPathError("export_regular_file_required", path)
    if info.st_nlink != 1:
        raise PersonalDataPathError("hardlinked_export_file", path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True)
class MarketOnlyExportPlan:
    """唯讀 metadata manifest；不複製檔案，也不宣稱內容／來源授權已核驗。"""

    paths: PersonalDataPaths
    destination_root: Path
    files: tuple[MarketExportFile, ...]

    def validate(self) -> None:
        self.paths.validate()
        destination = _directory(self.destination_root)
        for root in (self.paths.market_root, self.paths.personal_root, self.paths.legacy_output_root):
            _separate(destination, root)
        seen: set[Path] = set()
        for entry in self.files:
            relative = _market_relative(entry.relative_path)
            source = _absolute(self.paths.market_root / relative)
            if source != entry.source_path or not source.is_relative_to(self.paths.market_root):
                raise PersonalDataPathError("export_source_changed", source)
            if _overlap(source, self.paths.legacy_output_root):
                raise PersonalDataPathError("legacy_output_excluded", source)
            if source in seen:
                raise PersonalDataPathError("duplicate_export_file", source)
            seen.add(source)
            _absolute(destination / relative)
            if _file_identity(source) != entry.identity:
                raise PersonalDataPathError("export_file_changed", source)


def plan_market_only_export(
    paths: PersonalDataPaths,
    relative_files: Iterable[str],
    *,
    destination_root: str | Path,
) -> MarketOnlyExportPlan:
    """caller 明列檔案，固定白名單檢查；不 glob、不讀內容、不建立包或目的目錄。"""
    paths.validate()
    entries = []
    for raw in relative_files:
        source = _absolute(paths.market_root / _market_relative(raw))
        entries.append(MarketExportFile(raw, source, _file_identity(source)))
    plan = MarketOnlyExportPlan(paths, _absolute(destination_root), tuple(entries))
    plan.validate()
    return plan