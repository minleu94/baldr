"""在明示資料根目錄內有界尋找並驗證題材研究快照。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Literal

from app_module.theme_research_snapshot import ThemeResearchSnapshot, read_theme_research_snapshot


_PRICE_SCHEMA = "baldr.theme_research_snapshot.v1"
_FLOW_SCHEMA = "baldr.theme_research_snapshot.tpex_flows.v2"
_SCHEMA_BY_CHOICE = {"price-v1": _PRICE_SCHEMA, "flow-v2": _FLOW_SCHEMA}
_MAX_MANIFEST_BYTES = 32 * 1024
_MAX_DISCOVERY_MANIFESTS = 128
_MAX_DISCOVERY_ENTRIES = 4096
_MAX_DISCOVERY_BYTES = 4 * 1024 * 1024
_MAX_READER_BUDGET_BYTES = 256 * 1024 * 1024
_MAX_PRICE_BYTES = 64 * 1024 * 1024
_MAX_MAPPING_BYTES = 4 * 1024 * 1024
_MAX_FLOW_TREE_BYTES = 128 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True, slots=True)
class ThemeSnapshotCatalogEntry:
    """已由既有 reader 完整讀取並驗證的快照；metadata-only項目不會輸出為entry。"""

    manifest_path: Path
    schema: str
    data_date: date
    saved_completed_at: datetime
    identity_sha256: str
    snapshot: ThemeResearchSnapshot


@dataclass(frozen=True, slots=True)
class ThemeSnapshotRejection:
    """被拒絕的manifest或候選，以及不提升資格的原因。"""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class ThemeSnapshotCatalogResult:
    """一次有界解析結果；entries只含已驗證快照，metadata候選不代表可用。"""

    entries: tuple[ThemeSnapshotCatalogEntry, ...]
    rejections: tuple[ThemeSnapshotRejection, ...]
    candidate_count: int
    verified_count: int
    unverified_candidate_count: int
    limited: bool
    limit_reason: str | None

    @property
    def selected(self) -> ThemeSnapshotCatalogEntry | None:
        return self.entries[0] if self.entries else None


@dataclass(frozen=True, slots=True)
class _MetadataCandidate:
    path: Path
    schema: str
    data_date: date
    saved_completed_at: datetime
    identity_sha256: str
    metadata: dict[str, object]


class _CatalogLimitReached(ValueError):
    """有界檢查無法證明候選全集時，不可宣稱已找到latest。"""


class _CatalogCancelled(ValueError):
    """明確取消本次唯讀目錄解析。"""


def _is_reparse_or_symlink(path: Path) -> bool:
    info = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _assert_no_reparse_components(path: Path, *, stop: Path) -> None:
    """檢查caller root與其下路徑的每個既存元件，不跟隨junction或symlink。"""

    absolute = path.absolute()
    boundary = stop.absolute()
    try:
        relative = absolute.relative_to(boundary)
    except ValueError as exc:
        raise ValueError("路徑超出caller明選root") from exc
    chain = [boundary]
    current = boundary
    for part in relative.parts:
        current = current / part
        chain.append(current)
    for item in chain:
        if _is_reparse_or_symlink(item):
            raise ValueError("拒絕symlink或reparse路徑")


def _validate_root(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("root必須是caller明選的絕對Path")
    absolute = root.absolute()
    # 檢查到磁碟／UNC anchor，避免root本身或其父層是junction／symlink。
    anchor = Path(absolute.anchor)
    current = anchor
    for part in absolute.parts[1:]:
        current = current / part
        if not current.exists():
            raise ValueError("root路徑不存在")
        if _is_reparse_or_symlink(current):
            raise ValueError("root不得經由symlink或reparse進入")
    resolved = absolute.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("root必須是既存目錄")
    return resolved


def _check_cancel(cancel_callback: Callable[[], object] | None) -> None:
    if cancel_callback is not None and bool(cancel_callback()):
        raise _CatalogCancelled("題材快照目錄解析已取消")


def _read_small_manifest(path: Path) -> bytes:
    # 不依賴先前stat結果，避免檔案在檢查與讀取間被替換成大型內容。
    with path.open("rb") as stream:
        raw = stream.read(_MAX_MANIFEST_BYTES + 1)
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError("manifest超過32KiB上限")
    return raw


def _aware_datetime(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("saved_completed_at必須是含時區字串")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("saved_completed_at格式不合法") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("saved_completed_at必須含時區")
    return parsed


def _manifest_file(meta: dict[str, object], key: str, *, root: Path, base: Path,
                   maximum: int) -> tuple[Path, int]:
    record = meta.get(key)
    if type(record) is not dict or set(record) != {"path", "sha256"}:
        raise ValueError(f"{key}必須是path與sha256小manifest")
    relative_raw, digest = record["path"], record["sha256"]
    if (type(relative_raw) is not str or not relative_raw.strip() or Path(relative_raw).is_absolute()
            or type(digest) is not str or _SHA256.fullmatch(digest) is None):
        raise ValueError(f"{key}路徑或SHA256格式不合法")
    lexical = base / relative_raw
    try:
        _assert_no_reparse_components(lexical, stop=root)
        resolved = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{key}檔案不存在或路徑不合法") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"{key}檔案越界或不是一般檔案")
    _assert_no_reparse_components(resolved, stop=root)
    size = resolved.stat().st_size
    if size > maximum:
        raise ValueError(f"{key}檔案超過既有reader大小上限")
    return resolved, size


def _flow_tree_size(
    directory: Path, *, root: Path, cancel_callback: Callable[[], object] | None,
) -> int:
    """只檢查manifest明選的單一flow批次目錄，並限制樹大小與項目數。"""

    _assert_no_reparse_components(directory, stop=root)
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        raise ValueError("flow批次目錄須留在caller root內")
    total = 0
    visited = 0
    pending = [resolved]
    try:
        while pending:
            _check_cancel(cancel_callback)
            current = pending.pop()
            with os.scandir(current) as iterator:
                for child in iterator:
                    _check_cancel(cancel_callback)
                    if visited >= 512:
                        # 僅額外消耗第513項來證明超限，不先materialize完整目錄。
                        raise _CatalogLimitReached("flow批次項目數超出512項有界檢查上限")
                    visited += 1
                    _check_cancel(cancel_callback)
                    child_path = Path(child.path)
                    if _is_reparse_or_symlink(child_path):
                        raise ValueError("flow批次含symlink或reparse項目")
                    if child.is_dir(follow_symlinks=False):
                        pending.append(child_path)
                    elif child.is_file(follow_symlinks=False):
                        total += child.stat(follow_symlinks=False).st_size
                        if total > _MAX_FLOW_TREE_BYTES:
                            raise _CatalogLimitReached("flow批次超出128MiB檢查上限")
    except OSError as exc:
        raise _CatalogLimitReached("flow批次無法完整列舉，latest資格未確認") from exc
    return total


def _artifact_charge(meta: dict[str, object], schema: str, *, root: Path,
                     base: Path, cancel_callback: Callable[[], object] | None) -> int:
    _, mapping_size = _manifest_file(meta, "mapping", root=root, base=base,
                                     maximum=_MAX_MAPPING_BYTES)
    if schema == _PRICE_SCHEMA:
        _, price_size = _manifest_file(meta, "prices", root=root, base=base,
                                       maximum=_MAX_PRICE_BYTES)
        # 既有reader會多次核hash，並開啟SQLite；以三倍原件大小記帳。
        return 3 * (mapping_size + price_size)

    if "institutional" not in meta:
        raise ValueError("flow-v2缺少明選法人pin")
    institutional = meta["institutional"]
    expected = {"daily_directory", "manifest_sha256", "receipt_sha256", "source_use_path", "source_use_sha256"}
    if type(institutional) is not dict or set(institutional) != expected:
        raise ValueError("flow-v2法人pin欄位不完整")
    for key in ("manifest_sha256", "receipt_sha256", "source_use_sha256"):
        if type(institutional[key]) is not str or _SHA256.fullmatch(institutional[key]) is None:
            raise ValueError("flow-v2法人pin SHA256格式不合法")
    raw_dir, raw_policy = institutional["daily_directory"], institutional["source_use_path"]
    if type(raw_dir) is not str or type(raw_policy) is not str:
        raise ValueError("flow-v2法人pin路徑格式不合法")
    directory, policy = Path(raw_dir), Path(raw_policy)
    if not directory.is_absolute() or not policy.is_absolute():
        raise ValueError("flow-v2法人pin須為絕對路徑")
    _assert_no_reparse_components(directory, stop=root)
    _assert_no_reparse_components(policy, stop=root)
    resolved_policy = policy.resolve(strict=True)
    if not resolved_policy.is_relative_to(root) or not resolved_policy.is_file():
        raise ValueError("flow-v2用途原件須位於caller root內")
    policy_size = resolved_policy.stat().st_size
    if policy_size > 64 * 1024:
        raise ValueError("flow-v2用途原件超過64KiB")
    flow_size = _flow_tree_size(directory, root=root, cancel_callback=cancel_callback)
    return 3 * (mapping_size + policy_size + flow_size)


def _scan_manifests(
    root: Path, *, cancel_callback: Callable[[], object] | None,
) -> tuple[list[Path], list[ThemeSnapshotRejection], bool, str | None]:
    manifests: list[Path] = []
    rejections: list[ThemeSnapshotRejection] = []
    pending: list[tuple[Path, int]] = [(root, 0)]
    visited = 0
    limited = False
    reason: str | None = None
    while pending:
        _check_cancel(cancel_callback)
        directory, depth = pending.pop(0)
        try:
            with os.scandir(directory) as iterator:
                for child in iterator:
                    _check_cancel(cancel_callback)
                    if visited >= _MAX_DISCOVERY_ENTRIES:
                        # 僅額外消耗一項來確認超限，拒絕以局部目錄宣稱latest。
                        limited, reason = True, f"目錄項目超過{_MAX_DISCOVERY_ENTRIES}項上限"
                        return manifests, rejections, limited, reason
                    visited += 1
                    path = Path(child.path)
                    try:
                        if _is_reparse_or_symlink(path):
                            rejections.append(ThemeSnapshotRejection(path, "拒絕symlink或reparse項目"))
                            continue
                        if child.is_dir(follow_symlinks=False):
                            if depth < 2:
                                pending.append((path, depth + 1))
                            continue
                        if not child.is_file(follow_symlinks=False) or path.suffix.casefold() != ".json":
                            continue
                    except OSError as exc:
                        rejections.append(ThemeSnapshotRejection(path, f"無法檢查路徑：{exc}"))
                        return manifests, rejections, True, "目錄項目無法完整檢查"
                    if len(manifests) >= _MAX_DISCOVERY_MANIFESTS:
                        limited, reason = True, "JSON候選超過128個上限"
                        return manifests, rejections, limited, reason
                    manifests.append(path)
        except OSError as exc:
            rejections.append(ThemeSnapshotRejection(directory, f"無法列舉目錄：{exc}"))
            return manifests, rejections, True, "目錄無法完整列舉"
    return manifests, rejections, limited, reason


def resolve_latest_theme_research_snapshot(
    root: Path,
    *,
    known_at: datetime,
    schema: Literal["price-v1", "flow-v2"] = "price-v1",
    cancel_callback: Callable[[], object] | None = None,
) -> ThemeSnapshotCatalogResult:
    """從明選root以資料日、保存完成時排序並回傳最新合法快照。

    每個JSON manifest最多32KiB，搜尋root與兩層子目錄，最多128個manifest、
    4096個目錄項目及4MiB discovery讀量。reader候選按manifest日期排序，
    逐一驗證到第一個合法版本；只有該版本會進entries。讀取額度用於保守估計
    既有reader可能讀取的artifact bytes，不使用mtime或自製報告判斷資格。
    cancel_callback在掃描、metadata與候選邊界檢查；既有reader沒有取消介面，
    單次reader驗證不可中斷，完成後會立刻回應取消。
    """

    _check_cancel(cancel_callback)
    if not isinstance(known_at, datetime) or known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at必須是aware datetime")
    if schema not in _SCHEMA_BY_CHOICE:
        raise ValueError("schema只接受price-v1或flow-v2")
    selected_schema = _SCHEMA_BY_CHOICE[schema]
    resolved_root = _validate_root(root)
    _check_cancel(cancel_callback)
    manifests, rejections, limited, limit_reason = _scan_manifests(
        resolved_root, cancel_callback=cancel_callback,
    )
    discovery_bytes = 0
    candidates: list[_MetadataCandidate] = []
    for path in manifests:
        _check_cancel(cancel_callback)
        try:
            _assert_no_reparse_components(path, stop=resolved_root)
            raw = _read_small_manifest(path)
            discovery_bytes += len(raw)
            if discovery_bytes > _MAX_DISCOVERY_BYTES:
                limited, limit_reason = True, "manifest metadata總讀量超過4MiB"
                rejections.append(ThemeSnapshotRejection(path, "達到metadata讀取預算，後續候選未解析"))
                break
            meta_obj = json.loads(raw)
            if type(meta_obj) is not dict:
                raise ValueError("manifest頂層必須是object")
            meta = meta_obj
            if meta.get("schema") != selected_schema:
                continue
            _check_cancel(cancel_callback)
            try:
                day_raw = meta.get("data_date")
                if type(day_raw) is not str:
                    raise ValueError("data_date必須是ISO日期字串")
                data_date = date.fromisoformat(day_raw)
                if data_date.isoformat() != day_raw:
                    raise ValueError("data_date不是標準ISO日期")
                completed = _aware_datetime(meta.get("saved_completed_at"))
            except ValueError as exc:
                rejections.append(ThemeSnapshotRejection(path, str(exc)))
                continue
            candidates.append(_MetadataCandidate(
                path=path,
                schema=selected_schema,
                data_date=data_date,
                saved_completed_at=completed,
                identity_sha256=sha256(raw).hexdigest(),
                metadata=meta,
            ))
        except _CatalogCancelled:
            raise
        except (OSError, RuntimeError, json.JSONDecodeError, ValueError) as exc:
            rejections.append(ThemeSnapshotRejection(path, str(exc)))

    candidate_count = len(candidates)
    # 若發現階段被截斷，不能把局部排序冒稱為latest。
    if limited:
        return ThemeSnapshotCatalogResult((), tuple(rejections), candidate_count, 0,
                                          candidate_count, True, limit_reason)

    candidates.sort(key=lambda item: (item.data_date, item.saved_completed_at.astimezone(timezone.utc)),
                     reverse=True)
    reader_budget = 0
    attempted = 0
    for candidate in candidates:
        _check_cancel(cancel_callback)
        try:
            _assert_no_reparse_components(candidate.path, stop=resolved_root)
            charge = _artifact_charge(candidate.metadata, candidate.schema, root=resolved_root,
                                      base=candidate.path.parent, cancel_callback=cancel_callback)
            if reader_budget + charge > _MAX_READER_BUDGET_BYTES:
                limited, limit_reason = True, "既有reader artifact讀取預算達256MiB"
                rejections.append(ThemeSnapshotRejection(candidate.path, "候選未驗證：達到reader讀取預算"))
                break
            _check_cancel(cancel_callback)
            reader_budget += charge
            attempted += 1
            snapshot = read_theme_research_snapshot(
                candidate.path,
                known_at=known_at,
                expected_identity_sha256=candidate.identity_sha256,
            )
            # reader本身沒有取消介面；完成其單次有界讀取後立即回應取消。
            _check_cancel(cancel_callback)
            _assert_no_reparse_components(candidate.path, stop=resolved_root)
            entry = ThemeSnapshotCatalogEntry(
                manifest_path=candidate.path,
                schema=candidate.schema,
                data_date=candidate.data_date,
                saved_completed_at=candidate.saved_completed_at,
                identity_sha256=candidate.identity_sha256,
                snapshot=snapshot,
            )
            return ThemeSnapshotCatalogResult(
                (entry,), tuple(rejections), candidate_count, 1,
                max(0, candidate_count - attempted), False, None,
            )
        except _CatalogCancelled:
            raise
        except _CatalogLimitReached as exc:
            rejections.append(ThemeSnapshotRejection(candidate.path, str(exc)))
            limited, limit_reason = True, str(exc)
            break
        except (OSError, RuntimeError, ValueError) as exc:
            rejections.append(ThemeSnapshotRejection(candidate.path, str(exc)))

    return ThemeSnapshotCatalogResult(
        (), tuple(rejections), candidate_count, 0, max(0, candidate_count - attempted),
        limited, limit_reason,
    )
