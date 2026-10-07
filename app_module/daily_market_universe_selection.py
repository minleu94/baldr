"""完整保存母體的顯示查詢與原 child 下鑽；不讀最新行情、不產生快照。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from app_module.daily_market_universe_run import (
    DailyMarketUniverseRunReader, DailyMarketUniverseRunPage,
)
from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository, VerifiedDailyMarketSnapshot,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.rule_research_parent_capture import BoundedRuleResearchParentWriter


@dataclass(frozen=True, slots=True)
class UniverseResearchQuery:
    """來源與顯示查詢一併固定；跨來源不能套用舊查詢。"""
    output_root: str
    generation_identity_sha256: str
    manifest_sha256: str
    condition_keys: tuple[str, ...] = ("close_above_ma20",)
    combine_mode: str = "AND"
    state_filter: str = "all"
    sort_key: str = "stock_code"
    descending: bool = False
    stock_filter: str = ""
    page: int = 0
    page_size: int = 50

    def __post_init__(self) -> None:
        if not Path(self.output_root).is_absolute():
            raise ValueError("universe_query_root_not_absolute")
        for pin in (self.generation_identity_sha256, self.manifest_sha256):
            if len(pin) != 64 or any(char not in "0123456789abcdef" for char in pin):
                raise ValueError("universe_query_pin_invalid")
        if not self.condition_keys or len(set(self.condition_keys)) != len(self.condition_keys):
            raise ValueError("universe_query_conditions_invalid")
        if self.combine_mode not in {"AND", "OR"}:
            raise ValueError("universe_query_mode_invalid")

    def assert_reader(self, reader: DailyMarketUniverseRunReader) -> None:
        if (reader.output_root != Path(self.output_root).resolve()
                or reader.generation_identity_sha256 != self.generation_identity_sha256
                or reader.manifest_sha256 != self.manifest_sha256):
            raise ValueError("universe_query_source_changed")


@dataclass(frozen=True, slots=True)
class UniverseResearchPage:
    query: UniverseResearchQuery
    page: DailyMarketUniverseRunPage
    source: Mapping[str, Any]
    counts: Mapping[str, int]


def read_universe_research_page(query: UniverseResearchQuery,
        *, cancel_callback: Callable[[], bool] | None = None) -> UniverseResearchPage:
    """worker 內開關 reader，SQLite connection 不跨執行緒保存。"""
    if cancel_callback is not None and cancel_callback():
        raise ValueError("universe_query_cancelled")
    with DailyMarketUniverseRunReader.open(query.output_root, query.generation_identity_sha256) as reader:
        query.assert_reader(reader)
        page = reader.query(condition_keys=query.condition_keys, combine_mode=query.combine_mode,
            state_filter=query.state_filter, sort_key=query.sort_key, descending=query.descending,
            stock_filter=query.stock_filter, page=query.page, page_size=query.page_size)
        if cancel_callback is not None and cancel_callback():
            raise ValueError("universe_query_cancelled")
        return UniverseResearchPage(query, page, reader.source_descriptor, reader.counts)


def resolve_universe_stock_snapshot(query: UniverseResearchQuery, stock_code: str,
        *, cancel_callback: Callable[[], bool] | None = None
        ) -> tuple[DailyMarketResearchScreenerService, VerifiedDailyMarketSnapshot]:
    """完整母體的列沿原 parent pins 找原 child，缺列或排除列不借其他來源。"""
    if cancel_callback is not None and cancel_callback():
        raise ValueError("universe_stock_cancelled")
    with DailyMarketUniverseRunReader.open(query.output_root, query.generation_identity_sha256) as reader:
        query.assert_reader(reader)
        if stock_code not in reader.plan.included_stock_codes:
            raise ValueError("universe_stock_not_included")
        for segment in reader.manifest["segments"]:
            if cancel_callback is not None and cancel_callback():
                raise ValueError("universe_stock_cancelled")
            reference = segment.get("parent_reference")
            if not isinstance(reference, dict):
                continue
            parent = BoundedRuleResearchParentWriter(Path(reference["capture_root"]) / "parents", read_only=True).read(
                reference["capture_identity_sha256"])["capture"]
            for batch in parent["batches"]:
                if cancel_callback is not None and cancel_callback():
                    raise ValueError("universe_stock_cancelled")
                if stock_code not in batch["included_stock_codes"]:
                    continue
                root = Path(reference["snapshot_root"]) / "batches" / parent["plan_sha256"] / batch["batch_id"]
                snapshot = DailyMarketSnapshotRepository(root).load_manifest(
                    batch["manifest_sha256"], batch["cohort_id"], date.fromisoformat(reader.plan.decision_date.isoformat()),
                    expected_stock_codes=batch["included_stock_codes"])
                if cancel_callback is not None and cancel_callback():
                    raise ValueError("universe_stock_cancelled")
                config = SimpleNamespace(db_file=reader.plan.source_clock.source_binding["database"]
                    if reader.plan.source_clock is not None else None, output_root=None)
                return DailyMarketResearchScreenerService(config, snapshot_root=root), snapshot
    raise ValueError("universe_stock_child_missing")
