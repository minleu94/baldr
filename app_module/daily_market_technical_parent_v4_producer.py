"""由固定唯讀來源工作階段產製並保存技術研究 parent v4。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Literal

from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_snapshot_v4_producer import (
    DailyMarketTechnicalSnapshotV4ProducerError,
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.daily_market_technical_source import (
    DailyMarketTechnicalSourceError,
    _source_pin,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    ResearchCaptureWriteScope,
    RuleSampleCaptureError,
    _read_file,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    PARENT_RECEIPT_MAX_BYTES_V4,
    BoundedDailyMarketTechnicalParentCaptureWriterV4,
    DailyMarketTechnicalCohortV4,
    DailyMarketTechnicalParentPlanV4,
    DailyMarketTechnicalParentReceiptV4,
    TechnicalParentCaptureV4Error,
    build_daily_market_technical_parent_plan_v4,
)
from app_module.sqlite_read_only import ReadOperationCancelled


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DailyMarketTechnicalParentV4ProductionError(ValueError):
    """整合 v4 parent producer 的穩定錯誤碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentV4ProductionResult:
    """一次受控產製的結果；receipt 只代表實際保存的狀態。"""

    status: Literal["complete", "cancelled", "failed"]
    plan: DailyMarketTechnicalParentPlanV4 | None
    receipt: DailyMarketTechnicalParentReceiptV4 | None
    error_code: str | None
    resumed: bool

    @property
    def plan_identity_sha256(self) -> str | None:
        return self.plan.identity_sha256 if self.plan is not None else None

    @property
    def receipt_identity_sha256(self) -> str | None:
        return self.receipt.identity_sha256 if self.receipt is not None else None

    @property
    def receipt_content_sha256(self) -> str | None:
        return self.receipt.content_sha256 if self.receipt is not None else None


def produce_daily_market_technical_parent_v4(
    *,
    source_database: str | Path,
    cohort: DailyMarketTechnicalCohortV4,
    decision_cutoff: datetime,
    child_output_root: str | Path,
    parent_root: str | Path,
    research_scope: ResearchCaptureWriteScope | None,
    cancel_callback: Callable[[], bool] | None = None,
    resume_receipt_identity_sha256: str | None = None,
    expected_resume_receipt_sha256: str | None = None,
) -> DailyMarketTechnicalParentV4ProductionResult:
    """以一個來源快照完成 cohort，然後依序保存並核驗所有 child batches。

    取消若發生於來源 session 成功 ``finish`` 之前，不會建立 plan 或 receipt。
    續跑只讀取目前重建 plan 下明示的 receipt identity；不尋找 latest。
    ``expected_resume_receipt_sha256`` 是呼叫端可選的獨立內容 pin。未提供時，
    本函式只會對明示 receipt 的原始 bytes 計算讀取競態所需 SHA，再交給
    strict reader 驗證，不把該本機計算值視為獨立來源證據。
    """

    plan: DailyMarketTechnicalParentPlanV4 | None = None
    receipt: DailyMarketTechnicalParentReceiptV4 | None = None
    parent_writer: BoundedDailyMarketTechnicalParentCaptureWriterV4 | None = None
    resumed = resume_receipt_identity_sha256 is not None

    try:
        _validate_resume_pins(
            resume_receipt_identity_sha256,
            expected_resume_receipt_sha256,
        )
        if not isinstance(cohort, DailyMarketTechnicalCohortV4):
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_cohort_invalid"
            )
        checked_cancel = _checked_cancel_callback(cancel_callback)
        source_path, parent_writer, child_root = _prepare_storage(
            source_database=source_database,
            parent_root=parent_root,
            child_output_root=child_output_root,
            research_scope=research_scope,
        )

        try:
            with DailyMarketTechnicalReadSession(
                source_path,
                decision_cutoff,
                cancel_callback=checked_cancel,
            ) as session:
                source_clock = session.clock
                included = cohort.included_stock_codes
                for offset in range(
                    0,
                    len(included),
                    DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
                ):
                    session.load_batch(
                        included[
                            offset:offset + DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS
                        ]
                    )
                finished_windows = session.finish()
        except ReadOperationCancelled as exc:
            return _result(
                "cancelled", None, None, _exception_code(exc), resumed=False
            )

        # plan 只由 finish 已發布的完整不可變窗口建構。
        plan = build_daily_market_technical_parent_plan_v4(
            cohort,
            source_clock=source_clock,
            finished_windows=finished_windows,
        )
        windows_by_code = {window.stock_code: window for window in finished_windows}
        _revalidate_active_storage(
            source_path,
            source_clock,
            parent_writer,
            child_root,
            research_scope,
        )

        if resume_receipt_identity_sha256 is not None:
            receipt, package = _read_explicit_resume(
                parent_writer,
                plan,
                receipt_identity_sha256=resume_receipt_identity_sha256,
                expected_receipt_sha256=expected_resume_receipt_sha256,
                child_output_root=child_root,
            )
            if receipt.status == "complete":
                return _result("complete", plan, receipt, None, resumed=True)
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            receipt = parent_writer.resume(
                plan.identity_sha256,
                receipt.identity_sha256,
                expected_receipt_sha256=package["receipt_sha256"],
            )
        else:
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            receipt = parent_writer.start(plan)

        plan_batches = plan.to_dict()["batches"]
        recorded_batch_ids = {
            str(item["batch_id"]) for item in receipt.to_dict()["batch_artifacts"]
        }
        for batch in plan_batches:
            batch_id = str(batch["batch_id"])
            if batch_id in recorded_batch_ids:
                continue
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            if _cancel_requested(checked_cancel):
                _revalidate_active_storage(
                    source_path,
                    source_clock,
                    parent_writer,
                    child_root,
                    research_scope,
                )
                receipt = _mark_terminal(
                    parent_writer,
                    plan,
                    receipt,
                    status="cancelled",
                    error_code="technical_parent_v4_cancelled",
                )
                return _result("cancelled", plan, receipt, "technical_parent_v4_cancelled", resumed)

            stock_codes = tuple(str(code) for code in batch["expected_stock_codes"])
            if any(code not in windows_by_code for code in stock_codes):
                raise DailyMarketTechnicalParentV4ProductionError(
                    "technical_parent_v4_finished_window_missing"
                )
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            batch_result = write_daily_market_technical_snapshot_v4_batch(
                output_root=child_root,
                cohort=cohort,
                source_clock=source_clock,
                finished_windows=tuple(windows_by_code[code] for code in stock_codes),
                cancel_callback=checked_cancel,
                research_scope=research_scope,
            )
            if batch_result.status == "cancelled":
                error_code = batch_result.error_code or "technical_snapshot_v4_cancelled"
                _revalidate_active_storage(
                    source_path,
                    source_clock,
                    parent_writer,
                    child_root,
                    research_scope,
                )
                receipt = _mark_terminal(
                    parent_writer,
                    plan,
                    receipt,
                    status="cancelled",
                    error_code=error_code,
                )
                return _result("cancelled", plan, receipt, error_code, resumed)
            if batch_result.artifact is None:
                raise DailyMarketTechnicalParentV4ProductionError(
                    "technical_parent_v4_verified_child_missing"
                )
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            receipt = parent_writer.record_verified_batch(
                plan.identity_sha256,
                receipt.identity_sha256,
                expected_previous_receipt_sha256=receipt.content_sha256,
                artifact=batch_result.artifact,
            )
            recorded_batch_ids.add(batch_id)
            if _cancel_requested(checked_cancel):
                _revalidate_active_storage(
                    source_path,
                    source_clock,
                    parent_writer,
                    child_root,
                    research_scope,
                )
                receipt = _mark_terminal(
                    parent_writer,
                    plan,
                    receipt,
                    status="cancelled",
                    error_code="technical_parent_v4_cancelled",
                )
                return _result("cancelled", plan, receipt, "technical_parent_v4_cancelled", resumed)

        if _cancel_requested(checked_cancel):
            _revalidate_active_storage(
                source_path,
                source_clock,
                parent_writer,
                child_root,
                research_scope,
            )
            receipt = _mark_terminal(
                parent_writer,
                plan,
                receipt,
                status="cancelled",
                error_code="technical_parent_v4_cancelled",
            )
            return _result("cancelled", plan, receipt, "technical_parent_v4_cancelled", resumed)

        _revalidate_active_storage(
            source_path,
            source_clock,
            parent_writer,
            child_root,
            research_scope,
        )
        receipt = parent_writer.complete(
            plan.identity_sha256,
            receipt.identity_sha256,
            expected_previous_receipt_sha256=receipt.content_sha256,
        )
        return _result("complete", plan, receipt, None, resumed)
    except ReadOperationCancelled as exc:
        if parent_writer is not None and plan is not None and receipt is not None:
            try:
                receipt = _mark_terminal(
                    parent_writer,
                    plan,
                    receipt,
                    status="cancelled",
                    error_code="technical_parent_v4_cancelled",
                )
            except Exception:
                pass
        return _result(
            "cancelled", plan, receipt, _exception_code(exc), resumed
        )
    except Exception as exc:
        error_code = _exception_code(exc)
        if parent_writer is not None and plan is not None and receipt is not None:
            try:
                receipt = _mark_terminal(
                    parent_writer,
                    plan,
                    receipt,
                    status="failed",
                    error_code=error_code,
                )
            except Exception:
                # 保留最後可驗證 receipt；結果仍明示此輪未完成。
                pass
        return _result("failed", plan, receipt, error_code, resumed)


def _prepare_storage(
    *,
    source_database: str | Path,
    parent_root: str | Path,
    child_output_root: str | Path,
    research_scope: ResearchCaptureWriteScope | None,
) -> tuple[Path, BoundedDailyMarketTechnicalParentCaptureWriterV4, Path]:
    source_input = Path(source_database).expanduser()
    parent_input = Path(parent_root).expanduser()
    child_input = Path(child_output_root).expanduser()
    if not source_input.is_absolute() or not parent_input.is_absolute() or not child_input.is_absolute():
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_absolute_paths_required"
        )
    try:
        source_path = source_input.resolve(strict=True)
        if source_path != source_input:
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_source_path_not_canonical"
            )
        if research_scope is not None:
            if not isinstance(research_scope, ResearchCaptureWriteScope):
                raise DailyMarketTechnicalParentV4ProductionError(
                    "technical_parent_v4_scope_invalid"
                )
            research_scope.validate()
            if source_path != research_scope.source_database:
                raise DailyMarketTechnicalParentV4ProductionError(
                    "technical_parent_v4_scope_source_mismatch"
                )
        parent_guard = BoundedDailyMarketTechnicalParentCaptureWriterV4(
            parent_input,
            research_scope=research_scope,
        )
        child_guard = BoundedRuleResearchCaptureWriter(
            child_input,
            research_scope=research_scope,
        )
    except DailyMarketTechnicalParentV4ProductionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, RuleSampleCaptureError) as exc:
        raise DailyMarketTechnicalParentV4ProductionError(
            _exception_code(exc)
        ) from exc

    parent_path = parent_guard.output_root
    child_path = child_guard.output_root
    if _roots_overlap(parent_path, child_path):
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_output_roots_overlap"
        )
    wal_path = Path(f"{source_path}-wal")
    for root in (parent_path, child_path):
        if (
            source_path.is_relative_to(root)
            or root.is_relative_to(source_path)
            or wal_path.is_relative_to(root)
            or root.is_relative_to(wal_path)
        ):
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_source_output_overlap"
            )
    return source_path, parent_guard, child_path


def _read_explicit_resume(
    writer: BoundedDailyMarketTechnicalParentCaptureWriterV4,
    plan: DailyMarketTechnicalParentPlanV4,
    *,
    receipt_identity_sha256: str,
    expected_receipt_sha256: str | None,
    child_output_root: Path,
) -> tuple[DailyMarketTechnicalParentReceiptV4, dict[str, Any]]:
    if _SHA256_RE.fullmatch(receipt_identity_sha256) is None:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_identity_invalid"
        )
    receipt_path = (
        writer.store_root
        / "plans"
        / plan.identity_sha256
        / "receipts"
        / f"{receipt_identity_sha256}.json"
    )
    try:
        raw = _read_file(receipt_path, PARENT_RECEIPT_MAX_BYTES_V4)
    except (OSError, RuntimeError, RuleSampleCaptureError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_unavailable_for_current_plan"
        ) from exc
    content_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_receipt_sha256 is not None and expected_receipt_sha256 != content_sha256:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_hash_mismatch"
        )
    package = writer.read(
        plan.identity_sha256,
        receipt_identity_sha256,
        expected_receipt_sha256=content_sha256,
        expected_plan_sha256=plan.content_sha256,
    )
    if package["plan"] != plan.to_dict():
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_plan_mismatch"
        )
    receipt = DailyMarketTechnicalParentReceiptV4.from_dict(package["receipt"])
    if receipt.identity_sha256 != receipt_identity_sha256:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_identity_mismatch"
        )
    saved_child_root = receipt.to_dict()["repository_output_root"]
    if saved_child_root is not None and Path(saved_child_root) != child_output_root:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_child_root_mismatch"
        )
    return receipt, package


def _revalidate_active_storage(
    source_database: Path,
    source_clock: DailyMarketTechnicalSourceClockV4,
    parent_writer: BoundedDailyMarketTechnicalParentCaptureWriterV4,
    child_output_root: Path,
    research_scope: ResearchCaptureWriteScope | None,
) -> None:
    """每次 publish 邊界重驗原始來源 pin 與兩個輸出根。"""

    if research_scope is not None:
        research_scope.validate()
        if source_database != research_scope.source_database:
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_scope_source_mismatch"
            )
    current_pin = _source_pin(source_database)
    if current_pin is None or current_pin != source_clock.source_file_pin:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_source_pin_changed_after_finish"
        )
    parent_guard = BoundedDailyMarketTechnicalParentCaptureWriterV4(
        parent_writer.output_root,
        research_scope=research_scope,
    )
    child_guard = BoundedRuleResearchCaptureWriter(
        child_output_root,
        research_scope=research_scope,
    )
    if (
        parent_guard.output_root != parent_writer.output_root
        or child_guard.output_root != child_output_root
    ):
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_output_root_changed"
        )


def _validate_resume_pins(
    receipt_identity_sha256: str | None,
    expected_receipt_sha256: str | None,
) -> None:
    if receipt_identity_sha256 is None:
        if expected_receipt_sha256 is not None:
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_resume_hash_without_identity"
            )
        return
    if _SHA256_RE.fullmatch(receipt_identity_sha256) is None:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_identity_invalid"
        )
    if expected_receipt_sha256 is not None and _SHA256_RE.fullmatch(expected_receipt_sha256) is None:
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_resume_receipt_hash_invalid"
        )


def _checked_cancel_callback(
    callback: Callable[[], bool] | None,
) -> Callable[[], bool] | None:
    if callback is None:
        return None
    if not callable(callback):
        raise DailyMarketTechnicalParentV4ProductionError(
            "technical_parent_v4_cancel_callback_invalid"
        )

    def checked() -> bool:
        try:
            value = callback()
        except Exception as exc:
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_cancel_callback_failed"
            ) from exc
        if type(value) is not bool:
            raise DailyMarketTechnicalParentV4ProductionError(
                "technical_parent_v4_cancel_callback_invalid"
            )
        return value

    return checked


def _cancel_requested(callback: Callable[[], bool] | None) -> bool:
    return callback() if callback is not None else False


def _mark_terminal(
    writer: BoundedDailyMarketTechnicalParentCaptureWriterV4,
    plan: DailyMarketTechnicalParentPlanV4,
    receipt: DailyMarketTechnicalParentReceiptV4,
    *,
    status: Literal["failed", "cancelled"],
    error_code: str,
) -> DailyMarketTechnicalParentReceiptV4:
    if receipt.status != "partial":
        return receipt
    return writer.mark_terminal(
        plan.identity_sha256,
        receipt.identity_sha256,
        expected_previous_receipt_sha256=receipt.content_sha256,
        status=status,
        error_code=error_code,
    )


def _roots_overlap(left: Path, right: Path) -> bool:
    return (
        left == right
        or left.is_relative_to(right)
        or right.is_relative_to(left)
    )


def _exception_code(exc: BaseException) -> str:
    if isinstance(exc, ReadOperationCancelled):
        return "daily_technical_source_cancelled"
    code = getattr(exc, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,256}", code):
        return code
    if isinstance(exc, DailyMarketTechnicalSnapshotV4ProducerError):
        return exc.code
    if isinstance(exc, (DailyMarketTechnicalSourceError, TechnicalParentCaptureV4Error)):
        return str(getattr(exc, "code", "technical_parent_v4_production_failed"))
    return "technical_parent_v4_production_failed"


def _result(
    status: Literal["complete", "cancelled", "failed"],
    plan: DailyMarketTechnicalParentPlanV4 | None,
    receipt: DailyMarketTechnicalParentReceiptV4 | None,
    error_code: str | None,
    resumed: bool,
) -> DailyMarketTechnicalParentV4ProductionResult:
    return DailyMarketTechnicalParentV4ProductionResult(
        status=status,
        plan=plan,
        receipt=receipt,
        error_code=error_code,
        resumed=resumed,
    )
