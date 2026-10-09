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
        DailyMarketTechnicalUniverseV4ProductionRequest,
        DailyMarketTechnicalUniverseV4ProductionResult,
    )
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
        DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    )


class CurrentSelectionSourcePairError(ValueError):
    """混版或未明示時序時，不交付部分來源。"""


@dataclass(frozen=True)
class CurrentSelectionProductionOutcome:
    """保留真正產製狀態；未完成時不附保存 bundle。"""

    technical_result: DailyMarketTechnicalUniverseV4ProductionResult
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1 | None
    bundle_error_code: str | None = None


def produce_current_selection_bundle(
    writer: DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    *,
    production_request: DailyMarketTechnicalUniverseV4ProductionRequest,
    pointer_path: str | Path,
) -> CurrentSelectionProductionOutcome:
    """背景先選定來源，再沿原 request 產製；取消／失敗不保存部分結果。

    未來函數自查：只接受明示 request cutoff，雙來源在產製前核定；
    不改寫原 cutoff、不取後來 pointer，不改計算、母體或來源可得時間。
    """
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionRequest,
        produce_daily_market_technical_universe_v4,
    )
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleError,
    )

    if type(production_request) is not DailyMarketTechnicalUniverseV4ProductionRequest:
        raise CurrentSelectionSourcePairError("current_source_technical_request_type_invalid")
    cancel = production_request.cancel_callback
    pair = open_current_selection_source_pair(
        pointer_path, cutoff_at=production_request.decision_cutoff, cancel_callback=cancel,
    )
    _check_cancel(cancel)
    result = produce_daily_market_technical_universe_v4(production_request)
    if (result.status != "complete" or result.plan is None or result.receipt is None
            or result.receipt.status != "complete"):
        return CurrentSelectionProductionOutcome(result, None)
    try:
        reference = publish_completed_technical_selection_bundle(
            writer, production_result=result, store_output_root=production_request.store_output_root,
            source_pair=pair, cancel_callback=cancel,
        )
    except (DailyMarketTechnicalOfficialDispositionBundleError, CurrentSelectionSourcePairError, OSError) as exc:
        # 已保存的技術收據仍可查閱；官方 bundle 失敗不能顯示為完整聯合產製。
        code = getattr(exc, "code", None)
        return CurrentSelectionProductionOutcome(result, None, code if isinstance(code, str) else str(exc))
    return CurrentSelectionProductionOutcome(result, reference)


@dataclass(frozen=True)
class CurrentSelectionSourcePair:
    """程序內已讀回來源；下游 writer 仍須重新驗證 exact pins。"""

    market: CurrentMarketAssignmentReader
    disposal: CurrentOfficialDisposalReader
    cutoff_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.cutoff_at, datetime) or self.cutoff_at.utcoffset() is None:
            raise CurrentSelectionSourcePairError("current_source_aware_cutoff_required")
        _validate_pair_readers(self.market, self.disposal)


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


def _validate_pair_readers(
    market: CurrentMarketAssignmentReader, disposal: CurrentOfficialDisposalReader,
) -> None:
    if (type(market) is not CurrentMarketAssignmentReader
            or type(disposal) is not CurrentOfficialDisposalReader):
        raise CurrentSelectionSourcePairError("current_source_pair_reader_type_invalid")
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
    pair = CurrentSelectionSourcePair(market, disposal, cutoff)
    _check_cancel(cancel_callback)
    return pair


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
    store_output_root: str | Path,
    pointer_path: str | Path | None = None,
    source_pair: CurrentSelectionSourcePair | None = None,
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
    if (pointer_path is None) == (source_pair is None):
        raise CurrentSelectionSourcePairError("current_source_exactly_one_source_required")
    if source_pair is not None:
        if type(source_pair) is not CurrentSelectionSourcePair:
            raise CurrentSelectionSourcePairError("current_source_pair_type_invalid")
        if (not isinstance(source_pair.cutoff_at, datetime)
                or source_pair.cutoff_at.utcoffset() is None
                or source_pair.cutoff_at != plan.source_clock.decision_cutoff):
            raise CurrentSelectionSourcePairError("current_source_pair_technical_cutoff_mismatch")
        # 產製前選定的原來源 pins 不再從 mutable pointer 重選；writer 仍重核 exact 原件。
        _check_cancel(cancel_callback)
        return writer.create_from_pins(
            store_output_root=store_output_root,
            generation_identity_sha256=plan.generation_identity_sha256,
            plan_identity_sha256=plan.identity_sha256,
            expected_plan_sha256=production_result.plan_sha256 or "",
            receipt_identity_sha256=receipt.identity_sha256,
            expected_receipt_sha256=receipt.content_sha256,
            market_assignment_source_pin=source_pair.market.source_pin,
            official_disposal_source_pin=source_pair.disposal.source_pin,
            cancel_callback=cancel_callback,
        )
    assert pointer_path is not None
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
