"""保存規則來源選擇與跨頁查詢；不建立另一個保存庫或計算策略。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Callable, Any

from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository, VerifiedDailyMarketSnapshot,
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA, DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
)


@dataclass(frozen=True, slots=True)
class DailyResearchQuery:
    """僅描述同一保存來源的顯示查詢，不授予策略或模型資格。"""
    manifest_sha256: str
    manifest_identity_sha256: str
    condition_keys: tuple[str, ...]
    combine_mode: str = "AND"
    filter_state: str = "all"
    sort_key: str = "stock_code"
    descending: bool = False
    stock_filter: str = ""

    def __post_init__(self) -> None:
        for value in (self.manifest_sha256, self.manifest_identity_sha256):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("query_snapshot_pin_invalid")
        allowed = {"close_above_ma20", "close_above_ma60", "close_above_bbands30_upper"}
        if not self.condition_keys or len(set(self.condition_keys)) != len(self.condition_keys) or not set(self.condition_keys) <= allowed:
            raise ValueError("query_conditions_invalid")
        if self.combine_mode not in {"AND", "OR"} or self.filter_state not in {"all", "match", "no_match", "unknown"}:
            raise ValueError("query_mode_invalid")
        if self.sort_key not in {"stock_code", "data_date", "close", "ma20", "ma60", "bbands30_upper", "original_strength_rank"} or type(self.descending) is not bool:
            raise ValueError("query_sort_invalid")

    def assert_snapshot(self, snapshot: VerifiedDailyMarketSnapshot) -> None:
        if (self.manifest_sha256, self.manifest_identity_sha256) != (snapshot.manifest_sha256, snapshot.manifest_identity_sha256):
            raise ValueError("query_snapshot_changed")


@dataclass(frozen=True, slots=True)
class DailyResearchSourceSelection:
    """由原保存 manifest 取得的精確選擇；hash 不由使用者輸入。"""
    snapshot_root: Path
    cohort_id: str
    decision_date: date
    manifest_sha256: str
    manifest_identity_sha256: str
    feature_contract_version: str
    source_kind: str = "daily_market_research_snapshot"

    @property
    def label(self) -> str:
        return f"{self.decision_date.isoformat()}｜{self.cohort_id}｜{self.feature_contract_version}｜{self.snapshot_root}"


def resolve_daily_research_source_selection(manifest_path: str | Path) -> DailyResearchSourceSelection:
    """有界讀取所選原檔，再交原 repository 核整包，不猜 latest。"""
    path = Path(manifest_path).absolute()
    if path.parent.name != "manifests" or path.suffix != ".json":
        raise ValueError("source_not_daily_market_manifest")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("source_link_refused")
    stat = path.stat()
    if stat.st_nlink != 1 or stat.st_size > DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES:
        raise ValueError("source_manifest_budget_or_link")
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
        raise ValueError("source_schema_is_not_daily_market")
    digest = hashlib.sha256(raw).hexdigest()
    if path.stem != digest:
        raise ValueError("source_manifest_name_mismatch")
    root = path.parent.parent
    snapshot = DailyMarketSnapshotRepository(root).load_manifest(
        digest, manifest["cohort_id"], date.fromisoformat(manifest["decision_date"]),
    )
    if path.read_bytes() != raw:
        raise ValueError("source_manifest_changed")
    return DailyResearchSourceSelection(root, snapshot.cohort_id, snapshot.decision_date,
        snapshot.manifest_sha256, snapshot.manifest_identity_sha256,
        str(snapshot.manifest["feature_contract_version"]))


def list_daily_research_sources(config: object, *, snapshot_root: str | Path | None = None,
        cancel_callback: Callable[[], bool] | None = None) -> tuple[DailyResearchSourceSelection, ...]:
    """只查已選根與 OUTPUT_ROOT 的固定規則位置；不遞迴掃市場或私人資料。"""
    roots: list[Path] = []
    if snapshot_root is not None:
        roots.append(Path(snapshot_root))
    output = getattr(config, "output_root", None)
    if output is not None:
        roots.append(Path(output) / "research_snapshots" / "daily_market")
    selected: list[DailyResearchSourceSelection] = []
    visited: set[Path] = set()
    for root in roots:
        root = root.absolute()
        if root in visited:
            continue
        visited.add(root)
        manifests = root / "manifests"
        if not manifests.is_dir():
            continue
        for count, path in enumerate(manifests.iterdir()):
            if cancel_callback is not None and cancel_callback():
                return ()
            if count >= 256:
                raise ValueError("source_listing_budget_exceeded_choose_manifest")
            if path.suffix != ".json":
                continue
            # 錯來源不是空資料；整次查詢拒絕部分結果。
            selected.append(resolve_daily_research_source_selection(path))
    return tuple(sorted(selected, key=lambda item: (item.decision_date, item.cohort_id, item.manifest_sha256), reverse=True))


def read_selected_daily_research_source(selection: DailyResearchSourceSelection, config: object,
        *, cancel_callback: Callable[[], bool] | None = None) -> tuple[Any, VerifiedDailyMarketSnapshot]:
    """使用原 strict service 重驗來源；不寫設定、不產快照。"""
    from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
    service = DailyMarketResearchScreenerService(config, snapshot_root=selection.snapshot_root)
    snapshot = service.read_snapshot(selection.cohort_id, selection.decision_date,
        selection.manifest_sha256, cancel_callback=cancel_callback)
    if snapshot.manifest_identity_sha256 != selection.manifest_identity_sha256:
        raise ValueError("source_selection_identity_changed")
    return service, snapshot
