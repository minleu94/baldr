"""個人儲存與市場包的唯讀路徑契約；不建立目錄、不遷移或啟用 writer。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat
from threading import get_ident
from typing import Iterable, Iterator, Literal, Mapping
from urllib.parse import quote


class PersonalDataPathError(ValueError):
    """可供 caller 顯示的具名路徑拒絕。"""

    def __init__(self, code: str, path: str | Path = "") -> None:
        self.code = code
        super().__init__(f"{code}: {path}")


def _validate_absolute_syntax(path: str | Path) -> Path:
    """驗證 canonical path 的字面形式，不做 I/O，也不接受 OS device alias。"""
    value = Path(path).expanduser()
    if not value.is_absolute() or ".." in value.parts:
        raise PersonalDataPathError("absolute_path_required", value)
    if os.name == "nt":
        if str(value).startswith(("\\\\?\\", "\\\\.\\")):
            raise PersonalDataPathError("ambiguous_windows_path", value)
        # 拒絕 ADS、尾端正規化別名與 Windows 保留裝置名稱。
        for part in value.parts[1:]:
            if ":" in part or part.endswith((" ", ".")) or Path(part).is_reserved():
                raise PersonalDataPathError("ambiguous_windows_path", value)
    return value


def _strip_windows_io_prefix(path: str) -> str:
    if os.name != "nt":
        return path
    folded = path.casefold()
    unc_prefix = "\\\\?\\unc\\"
    if folded.startswith(unc_prefix):
        return "\\\\" + path[len(unc_prefix):]
    if folded.startswith("\\\\?\\"):
        return path[4:]
    return path


def _windows_utf16_units(path: str) -> int:
    return len(path.encode("utf-16-le")) // 2


def _render_internal_io_path(canonical_path: str | Path) -> str:
    """把已通過字面檢查的路徑轉成 OS 呼叫使用的形式。"""
    value = _validate_absolute_syntax(canonical_path)
    raw = str(value)
    if os.name != "nt" or _windows_utf16_units(raw) < 248:
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw.lstrip("\\")
    return "\\\\?\\" + raw


_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES = 4096
_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES = 1024 * 1024
_PAGE_PATH_RENDER_PATH_TYPE = type(Path())


class _PageOperationPathRenderMemo:
    """只在單次 P01 page operation 暫存已驗證的純路徑渲染。"""

    __slots__ = ("_values", "_used_utf16_bytes", "_closed", "_owner_thread_id")

    def __init__(self) -> None:
        self._values: dict[tuple[type[Path], str], str] = {}
        self._used_utf16_bytes = 0
        self._closed = False
        self._owner_thread_id = get_ident()

    @staticmethod
    def _utf16_byte_size(value: str) -> int:
        return len(value.encode("utf-16-le", errors="surrogatepass"))

    def render(self, path: str | Path) -> str:
        if (
            self._closed
            or not isinstance(path, Path)
            or type(path) is not _PAGE_PATH_RENDER_PATH_TYPE
            or not path.is_absolute()
            or get_ident() != self._owner_thread_id
        ):
            return _render_internal_io_path(path)

        # Path 在 Windows 上的 equality 會忽略大小寫，因此以原始 lexical 字串作 key。
        lexical_path = str(path)
        key = (type(path), lexical_path)
        cached = self._values.get(key)
        if cached is not None:
            return cached

        rendered = _render_internal_io_path(path)
        entry_bytes = self._utf16_byte_size(lexical_path) + self._utf16_byte_size(rendered)
        if (
            len(self._values) < _PAGE_PATH_RENDER_MEMO_MAX_ENTRIES
            and self._used_utf16_bytes + entry_bytes
            <= _PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES
        ):
            self._values[key] = rendered
            self._used_utf16_bytes += entry_bytes
        # 容量滿時只停止新增 memo；本次轉換仍已通過原 strict renderer。
        return rendered

    def clear(self) -> None:
        self._values.clear()
        self._used_utf16_bytes = 0
        self._closed = True


_PAGE_OPERATION_PATH_RENDER_MEMO: ContextVar[_PageOperationPathRenderMemo | None] = (
    ContextVar("p01_page_operation_path_render_memo", default=None)
)


@contextmanager
def _p01_page_operation_path_render_scope() -> Iterator[None]:
    """建立獨立且有界的 page memo；巢狀操作結束後恢復外層 scope。"""
    memo = _PageOperationPathRenderMemo()
    token = _PAGE_OPERATION_PATH_RENDER_MEMO.set(memo)
    try:
        yield
    finally:
        memo.clear()
        _PAGE_OPERATION_PATH_RENDER_MEMO.reset(token)


@contextmanager
def _suspend_p01_page_operation_path_render_scope() -> Iterator[None]:
    """讓 strict API 或外部回呼不會繼承 page memo。"""
    token = _PAGE_OPERATION_PATH_RENDER_MEMO.set(None)
    try:
        yield
    finally:
        _PAGE_OPERATION_PATH_RENDER_MEMO.reset(token)


def to_internal_io_path(path: str | Path) -> str:
    """僅渲染 OS I/O 形式；caller 須先做路徑守衛並保留 canonical identity。"""
    memo = _PAGE_OPERATION_PATH_RENDER_MEMO.get()
    if memo is not None:
        return memo.render(path)
    return _render_internal_io_path(path)


def to_internal_sqlite_uri(
    path: str | Path, mode: Literal["ro", "rw"]
) -> str:
    """輸出 SQLite URI；extended path 只存在 URI 內，不回傳作為 identity。"""
    if mode not in {"ro", "rw"}:
        raise PersonalDataPathError("unsupported_sqlite_mode", mode)
    io_path = _render_internal_io_path(path)
    return f"file:{quote(io_path, safe='/:')}?mode={mode}"


def _reject_links(path: Path) -> None:
    # lstat 保留 link 身分；Windows reparse 包含 junction，不僅 symlink。
    for component in reversed((path, *path.parents)):
        try:
            info = os.lstat(_render_internal_io_path(component))
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PersonalDataPathError("path_unavailable", component) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PersonalDataPathError("linked_path", component)


def _absolute(path: str | Path) -> Path:
    value = _validate_absolute_syntax(path)
    _reject_links(value)
    try:
        resolved = os.path.realpath(_render_internal_io_path(value))
        return Path(_strip_windows_io_prefix(resolved))
    except (OSError, RuntimeError) as exc:
        raise PersonalDataPathError("path_unavailable", value) from exc


def _directory(path: Path) -> Path:
    value = _absolute(path)
    io_path = _render_internal_io_path(value)
    if os.path.exists(io_path) and not os.path.isdir(io_path):
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
        # 使用者指定唯一市場包內個人子樹；其他重疊仍拒絕。
        if personal != market / "personal":
            _separate(market, personal)
        _separate(output, personal)
        # 個人子路徑未建立也檢查既有祖先，阻擋日後新增的 link 逃逸。
        for child in (self.watchlist_db, self.activation_marker, self.conversion_receipt,
                      self.backup_root, self.marker_backup_root,
                      self.research_notes_root, self.ledger_root):
            if not _absolute(child).is_relative_to(personal):
                raise PersonalDataPathError("personal_path_escape", child)
            try:
                info = os.lstat(_render_internal_io_path(child))
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
    if parts[0].casefold() == "personal":
        raise PersonalDataPathError("personal_subtree_excluded", raw)
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
        info = os.stat(_render_internal_io_path(path))
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
            if _overlap(source, self.paths.personal_root):
                raise PersonalDataPathError("personal_subtree_excluded", source)
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
    """caller 明列市場 CSV；不 glob／複製／開庫／分享。

    DATA_ROOT/personal 是使用者資料，FA_Data 整包不能直接分享；CSV manifest
    不代表市場 SQLite 表分享契約，也不解析 CSV 的私人內容。
    """
    paths.validate()
    entries = []
    for raw in relative_files:
        source = _absolute(paths.market_root / _market_relative(raw))
        entries.append(MarketExportFile(raw, source, _file_identity(source)))
    plan = MarketOnlyExportPlan(paths, _absolute(destination_root), tuple(entries))
    plan.validate()
    return plan

@dataclass(frozen=True)
class WatchlistCowControlPaths:
    """明示 COW 控制平面；舊來源僅為 root 外的相容唯讀輸入。"""

    personal_paths: PersonalDataPaths
    source_path: Path

    @property
    def marker_path(self) -> Path:
        return self.personal_paths.activation_marker

    @property
    def receipt_path(self) -> Path:
        return self.personal_paths.conversion_receipt

    @property
    def lock_path(self) -> Path:
        return self.marker_path.with_name(self.marker_path.name + ".lock")

    @property
    def source_backup_path(self) -> Path:
        import hashlib
        identity = hashlib.sha256(str(_absolute(self.source_path)).encode("utf-8")).hexdigest()
        return self.personal_paths.backup_root / f"source.{identity}.json"

    def backup_marker_path(self, activation_id: str) -> Path:
        if len(activation_id) != 32 or any(c not in "0123456789abcdef" for c in activation_id):
            raise PersonalDataPathError("invalid_activation_id", activation_id)
        return self.personal_paths.marker_backup_root / f"rollback.{activation_id}.json"

    def assert_personal(self, path: str | Path) -> Path:
        self.personal_paths.validate()
        value = _absolute(path)
        if not value.is_relative_to(self.personal_paths.personal_root):
            raise PersonalDataPathError("control_path_outside_personal", value)
        try:
            info = os.lstat(_render_internal_io_path(value))
        except FileNotFoundError:
            return value
        except OSError as exc:
            raise PersonalDataPathError("path_unavailable", value) from exc
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise PersonalDataPathError("hardlinked_control_file", value)
        return value

    def validate(self, source: str | Path, target: str | Path,
                 receipt_path: str | Path | None = None) -> None:
        self.personal_paths.validate()
        source_value = _absolute(source)
        expected_source = _absolute(self.source_path)
        if source_value != expected_source:
            raise PersonalDataPathError("control_source_mismatch", source_value)
        # personal 在 market 內時不能被誤認為 legacy 市場來源。
        if source_value.is_relative_to(self.personal_paths.personal_root):
            raise PersonalDataPathError("source_in_personal_subtree", source_value)
        if not any(source_value.is_relative_to(root) for root in
                   (self.personal_paths.market_root, self.personal_paths.legacy_output_root)):
            raise PersonalDataPathError("source_outside_legacy_root", source_value)
        for suffix in (".active", ".cow-active.json"):
            legacy_marker = _absolute(source_value.with_name(source_value.name + suffix))
            marker_path = _render_internal_io_path(legacy_marker)
            if os.path.isfile(marker_path) and os.stat(marker_path).st_nlink != 1:
                raise PersonalDataPathError("source_path_alias", legacy_marker)
        info = os.stat(_render_internal_io_path(source_value))
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PersonalDataPathError("source_path_alias", source_value)
        if self.assert_personal(target) != self.personal_paths.watchlist_db:
            raise PersonalDataPathError("control_target_mismatch", target)
        receipt = self.receipt_path if receipt_path is None else receipt_path
        if self.assert_personal(receipt) != self.receipt_path:
            raise PersonalDataPathError("control_receipt_mismatch", receipt)
        for path in (self.marker_path, self.lock_path, self.source_backup_path):
            self.assert_personal(path)

    def prepare_directories(self) -> None:
        """只由已明示執行的 convert／activate 呼叫，讀取與 preview 不建立。"""
        self.validate(self.source_path, self.personal_paths.watchlist_db)
        for directory in (self.marker_path.parent, self.personal_paths.backup_root,
                          self.personal_paths.marker_backup_root):
            canonical = self.assert_personal(directory)
            Path(_render_internal_io_path(canonical)).mkdir(parents=True, exist_ok=True)
            self.assert_personal(directory)
