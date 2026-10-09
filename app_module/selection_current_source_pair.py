"""將正常 current-status capture 的同版雙來源交給既有保存 writer。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from data_module.selection_market_assignments import CurrentMarketAssignmentReader
from data_module.selection_official_events import CurrentOfficialDisposalReader

if TYPE_CHECKING:
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionResult,
    )
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
        DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    )


class CurrentSelectionSourcePairError(ValueError):
    """混版或未明示時序時，不交付部分來源。"""


@dataclass(frozen=True)
class CurrentSelectionSourcePair:
    """程序內已讀回來源；下游 writer 仍須重新驗證 exact pins。"""

    market: CurrentMarketAssignmentReader
    disposal: CurrentOfficialDisposalReader
    cutoff_at: datetime


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        raise CurrentSelectionSourcePairError("current_source_cancel_callback_invalid")
    cancelled = callback()
    if type(cancelled) is not bool:
        raise CurrentSelectionSourcePairError("current_source_cancel_result_invalid")
    if cancelled:
        raise CurrentSelectionSourcePairError("current_source_pair_cancelled")


def open_current_selection_source_pair(
    pointer_path: str | Path,
    *,
    cutoff_at: datetime,
    cancel_callback: Callable[[], bool] | None = None,
) -> CurrentSelectionSourcePair:
    """成對讀指定 updater 指標；讀取中前進的混版一律拒絕。"""
    if not isinstance(cutoff_at, datetime) or cutoff_at.utcoffset() is None:
        raise CurrentSelectionSourcePairError("current_source_aware_cutoff_required")
    cutoff = cutoff_at.astimezone(timezone.utc)
    _check_cancel(cancel_callback)
    market = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=cutoff)
    _check_cancel(cancel_callback)
    disposal = CurrentOfficialDisposalReader.from_pointer(pointer_path, cutoff_at=cutoff)
    shared_fields = (
        "output_root", "run_id", "pointer_sha256",
        "snapshot_relative_path", "snapshot_sha256",
        "manifest_relative_path", "manifest_sha256", "snapshot_partial_failure",
    )
    if any(
        getattr(market.source_pin, field) != getattr(disposal.source_pin, field)
        for field in shared_fields
    ):
        raise CurrentSelectionSourcePairError("current_source_pair_version_mismatch")
    # 兩個既有 reader 的微秒輸出格式不同；原 pointer／snapshot bytes 仍須完全相同。
    for field in ("pointer_published_at", "snapshot_observed_at"):
        market_time = datetime.fromisoformat(getattr(market.source_pin, field))
        disposal_time = datetime.fromisoformat(getattr(disposal.source_pin, field))
        if (market_time.utcoffset() is None or disposal_time.utcoffset() is None
                or market_time != disposal_time):
            raise CurrentSelectionSourcePairError("current_source_pair_clock_mismatch")
    _check_cancel(cancel_callback)
    return CurrentSelectionSourcePair(market, disposal, cutoff)


def publish_current_selection_bundle(
    writer: DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    *,
    pointer_path: str | Path,
    cutoff_at: datetime,
    store_output_root: str | Path,
    generation_identity_sha256: str,
    plan_identity_sha256: str,
    expected_plan_sha256: str,
    receipt_identity_sha256: str,
    expected_receipt_sha256: str,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalOfficialDispositionBundleReferenceV1:
    """正常來源選版後只傳 exact pins，沿原 writer 的時序與發布 gate。"""
    pair = open_current_selection_source_pair(
        pointer_path, cutoff_at=cutoff_at, cancel_callback=cancel_callback,
    )
    _check_cancel(cancel_callback)
    return writer.create_from_pins(
        store_output_root=store_output_root,
        generation_identity_sha256=generation_identity_sha256,
        plan_identity_sha256=plan_identity_sha256,
        expected_plan_sha256=expected_plan_sha256,
        receipt_identity_sha256=receipt_identity_sha256,
        expected_receipt_sha256=expected_receipt_sha256,
        market_assignment_source_pin=pair.market.source_pin,
        official_disposal_source_pin=pair.disposal.source_pin,
        cancel_callback=cancel_callback,
    )


def publish_completed_technical_selection_bundle(
    writer: DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    *,
    production_result: DailyMarketTechnicalUniverseV4ProductionResult,
    pointer_path: str | Path,
    store_output_root: str | Path,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalOfficialDispositionBundleReferenceV1:
    """完整技術產製才交付保存；來源截止時間沿原 plan，不重寫為現在。"""
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionResult,
    )

    _check_cancel(cancel_callback)
    if type(production_result) is not DailyMarketTechnicalUniverseV4ProductionResult:
        raise CurrentSelectionSourcePairError("current_source_technical_result_type_invalid")
    plan = production_result.plan
    receipt = production_result.receipt
    if (production_result.status != "complete" or plan is None or receipt is None
            or receipt.status != "complete"):
        raise CurrentSelectionSourcePairError("current_source_technical_result_incomplete")
    # 這些 pins 由真正產製結果取出；下游 writer 仍須讀回並核驗 store 原件。
    return publish_current_selection_bundle(
        writer,
        pointer_path=pointer_path,
        cutoff_at=plan.source_clock.decision_cutoff,
        store_output_root=store_output_root,
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        expected_plan_sha256=production_result.plan_sha256 or "",
        receipt_identity_sha256=receipt.identity_sha256,
        expected_receipt_sha256=receipt.content_sha256,
        cancel_callback=cancel_callback,
    )
