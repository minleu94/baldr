"""以固定來源時計協調完整母體的技術研究 v4 保存。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any, Literal
from uuid import uuid4

from app_module.daily_market_technical_parent_v4_producer import (
    DailyMarketTechnicalParentV4ProductionResult,
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_read_session import (
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4Receipt,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreWriter,
    DailyMarketTechnicalUniverseV4VerifiedState,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    ResearchCaptureWriteScope,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
    DailyMarketTechnicalParentPlanV4,
    DailyMarketTechnicalParentReceiptV4,
    read_daily_market_technical_parent_capture_v4,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_MAX_CHARS = 160


class DailyMarketTechnicalUniverseV4ProductionError(ValueError):
    """完整母體協調器可供 caller 判讀的穩定錯誤碼。"""

    def __init__(self, code: str, *, cause_code: str = "") -> None:
        self.code = code
        self.cause_code = cause_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ProductionRequest:
    """一次完整母體產製或明示續跑的不可變請求。"""

    source_database: str | Path
    cohort: DailyMarketTechnicalUniverseV4Cohort
    decision_cutoff: datetime
    store_output_root: str | Path
    research_scope: ResearchCaptureWriteScope | None = None
    cancel_callback: Callable[[], bool] | None = None
    resume_receipt_identity_sha256: str | None = None
    expected_resume_receipt_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Preflight:
    """只讀預檢結果；建立 plan 但不建立任何輸出目錄或收據。"""

    source_database: Path
    store_output_root: Path
    segment_output_root: Path
    research_scope: ResearchCaptureWriteScope | None
    plan: DailyMarketTechnicalUniverseV4Plan
    plan_sha256: str
    calculation_identity_sha256: str
    resume_state: DailyMarketTechnicalUniverseV4VerifiedState | None


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ProductionResult:
    """一次完整母體 run 的保存狀態，不把部分 segments 升格為完成。"""

    status: Literal["complete", "cancelled", "failed"]
    step: str
    plan: DailyMarketTechnicalUniverseV4Plan | None
    receipt: DailyMarketTechnicalUniverseV4Receipt | None
    error_code: str | None
    cause_code: str | None
    resumed: bool
    calculation_identity_sha256: str | None
    completed_segment_indices: tuple[int, ...]
    missing_data_stock_codes: tuple[str, ...]

    @property
    def plan_identity_sha256(self) -> str | None:
        return self.plan.identity_sha256 if self.plan is not None else None

    @property
    def plan_sha256(self) -> str | None:
        if self.plan is None:
            return None
        return hashlib.sha256(self.plan.to_json().encode("utf-8")).hexdigest()

    @property
    def generation_identity_sha256(self) -> str | None:
        return self.plan.generation_identity_sha256 if self.plan is not None else None

    @property
    def receipt_identity_sha256(self) -> str | None:
        return self.receipt.identity_sha256 if self.receipt is not None else None

    @property
    def receipt_content_sha256(self) -> str | None:
        return self.receipt.content_sha256 if self.receipt is not None else None

    def to_dict(self) -> dict[str, object]:
        """輸出可序列化的進度摘要，明確分開分母、處理段與缺件。"""

        plan_payload = self.plan.to_dict() if self.plan is not None else None
        receipt_payload = self.receipt.to_dict() if self.receipt is not None else None
        cohort = self.plan.cohort if self.plan is not None else None
        population_state = cohort.population_state if cohort is not None else None
        child_batches_zero = (
            self.status == "complete"
            and cohort is not None
            and not cohort.included_stock_codes
        )
        return {
            "schema_version": "daily-market-technical-universe-v4-production-result.v1",
            "status": self.status,
            "step": self.step,
            "error_code": self.error_code,
            "cause_code": self.cause_code,
            "resumed": self.resumed,
            "generation_identity_sha256": self.generation_identity_sha256,
            "plan_identity_sha256": self.plan_identity_sha256,
            "plan_sha256": self.plan_sha256,
            "source_clock_identity_sha256": (
                plan_payload.get("source_clock_identity_sha256")
                if isinstance(plan_payload, Mapping)
                else None
            ),
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "calculation_identity_binding": (
                "每個 parent 的 source evidence 都逐筆核對；full generation identity 本身不含此 SHA。"
            ),
            "population_state": population_state,
            "segment_count": len(self.plan.segments) if self.plan is not None else 0,
            "parent_segment_count": len(self.completed_segment_indices),
            "completed_segment_indices": list(self.completed_segment_indices),
            "missing_data_stock_codes": list(self.missing_data_stock_codes),
            "counts": (
                receipt_payload.get("counts")
                if isinstance(receipt_payload, Mapping)
                else None
            ),
            "zero_child_batches": child_batches_zero,
            "zero_child_batch_note": (
                (
                    "完整排除 segment 仍保存已核驗的 complete parent metadata receipt；"
                    "該 parent 不含納入股票或 child batch。"
                    if population_state == "all_excluded"
                    else "宣告母體為空，沒有 segment、parent 或 child batch。"
                )
                if child_batches_zero
                else None
            ),
            "plan": plan_payload,
            "receipt": receipt_payload,
        }


def preflight_daily_market_technical_universe_v4(
    request: DailyMarketTechnicalUniverseV4ProductionRequest,
) -> DailyMarketTechnicalUniverseV4Preflight:
    """唯讀固定 source clock、方法身份與 full plan，不建立輸出或假收據。"""

    try:
        source_database = _canonical_source_database(request.source_database)
        cohort = request.cohort
        if not isinstance(cohort, DailyMarketTechnicalUniverseV4Cohort):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_cohort_invalid"
            )
        scope = request.research_scope
        if scope is not None:
            if not isinstance(scope, ResearchCaptureWriteScope):
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_research_scope_invalid"
                )
            scope.validate()
            if source_database != scope.source_database:
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_scope_source_mismatch"
                )

        initial_calculation_identity = _current_calculation_identity()
        source_clock = _read_source_clock(source_database, request.decision_cutoff)
        final_initial_calculation_identity = _current_calculation_identity()
        if initial_calculation_identity != final_initial_calculation_identity:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_calculation_changed_during_preflight"
            )

        try:
            plan = DailyMarketTechnicalUniverseV4Plan.build(
                cohort,
                source_clock=source_clock,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_plan_invalid",
                cause_code=_exception_code(exc),
            ) from exc

        output_root_input = _absolute_output_path(request.store_output_root)
        try:
            store_writer = DailyMarketTechnicalUniverseV4StoreWriter(
                output_root_input,
                research_scope=scope,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_store_root_invalid",
                cause_code=_exception_code(exc),
            ) from exc
        store_output_root = store_writer.output_root
        if not store_output_root.name:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_store_root_invalid"
            )
        segment_output_root = store_output_root.with_name(
            f"{store_output_root.name}_segments"
        )
        _validate_storage_roots(
            source_database=source_database,
            store_output_root=store_output_root,
            segment_output_root=segment_output_root,
            research_scope=scope,
        )

        plan_sha256 = hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()
        resume_id = request.resume_receipt_identity_sha256
        resume_sha = request.expected_resume_receipt_sha256
        if (resume_id is None) != (resume_sha is None):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_resume_pins_incomplete"
            )
        resume_state: DailyMarketTechnicalUniverseV4VerifiedState | None = None
        if resume_id is not None and resume_sha is not None:
            if not _is_sha256(resume_id) or not _is_sha256(resume_sha):
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_resume_pins_invalid"
                )
            try:
                resume_state = store_writer.read_exact(
                    plan.generation_identity_sha256,
                    plan.identity_sha256,
                    resume_id,
                    expected_receipt_sha256=resume_sha,
                    expected_plan_sha256=plan_sha256,
                )
            except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_resume_unavailable_for_current_cohort_and_clock",
                    cause_code=_exception_code(exc),
                ) from exc
            if resume_state.plan.to_json() != plan.to_json():
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_resume_plan_mismatch"
                )
            if resume_state.receipt.status not in {
                "partial", "cancelled", "failed", "complete"
            }:
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_resume_status_invalid"
                )
            if (
                resume_state.calculation_identity_sha256 is not None
                and resume_state.calculation_identity_sha256
                != initial_calculation_identity
            ):
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_saved_parent_calculation_identity_mismatch"
                )
            _verify_saved_parent_calculation_identities(
                resume_state,
                expected_calculation_identity_sha256=initial_calculation_identity,
            )

        return DailyMarketTechnicalUniverseV4Preflight(
            source_database=source_database,
            store_output_root=store_output_root,
            segment_output_root=segment_output_root,
            research_scope=scope,
            plan=plan,
            plan_sha256=plan_sha256,
            calculation_identity_sha256=initial_calculation_identity,
            resume_state=resume_state,
        )
    except DailyMarketTechnicalUniverseV4ProductionError:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_preflight_failed",
            cause_code=_exception_code(exc),
        ) from exc


def produce_daily_market_technical_universe_v4(
    request: DailyMarketTechnicalUniverseV4ProductionRequest,
) -> DailyMarketTechnicalUniverseV4ProductionResult:
    """產製或明示續跑完整 full-N 技術來源版本。"""

    try:
        preflight = preflight_daily_market_technical_universe_v4(request)
    except DailyMarketTechnicalUniverseV4ProductionError as exc:
        return _failed_result(
            "preflight",
            error_code=exc.code,
            cause_code=exc.cause_code,
        )

    plan = preflight.plan
    try:
        writer = DailyMarketTechnicalUniverseV4StoreWriter(
            preflight.store_output_root,
            research_scope=preflight.research_scope,
        )
    except Exception as exc:
        return _result(
            status="failed",
            step="writer_initialization",
            plan=plan,
            receipt=None,
            error_code="technical_universe_v4_store_root_invalid",
            cause_code=_exception_code(exc),
            resumed=preflight.resume_state is not None,
            calculation_identity_sha256=preflight.calculation_identity_sha256,
            completed_segments=[],
            missing_data_codes=set(),
        )
    receipt: DailyMarketTechnicalUniverseV4Receipt | None = None
    completed_segments: list[int] = []
    missing_data_codes: set[str] = set()
    resumed = preflight.resume_state is not None
    step = "start"

    try:
        if preflight.resume_state is None:
            receipt = writer.start(plan)
        else:
            state = preflight.resume_state
            receipt = state.receipt
            completed_segments.extend(index for index, _ref in state.segment_parent_references)
            missing_data_codes.update(state.missing_data_stock_codes)
            if receipt.status == "complete":
                return _result(
                    status="complete",
                    step="already_complete",
                    plan=plan,
                    receipt=receipt,
                    resumed=True,
                    calculation_identity_sha256=preflight.calculation_identity_sha256,
                    completed_segments=completed_segments,
                    missing_data_codes=missing_data_codes,
                )
            if receipt.status in {"cancelled", "failed"}:
                receipt = writer.resume(
                    plan.generation_identity_sha256,
                    plan.identity_sha256,
                    receipt.identity_sha256,
                    expected_previous_receipt_sha256=receipt.content_sha256,
                )

        step = "initial_cancel_check"
        if _cancel_requested(request.cancel_callback):
            receipt = _mark_terminal(
                writer,
                plan,
                receipt,
                status="cancelled",
                error_code="technical_universe_v4_cancelled",
            )
            return _result(
                status="cancelled",
                step=step,
                plan=plan,
                receipt=receipt,
                resumed=resumed,
                calculation_identity_sha256=preflight.calculation_identity_sha256,
                completed_segments=completed_segments,
                missing_data_codes=missing_data_codes,
            )

        for segment_index in range(len(plan.segments)):
            if segment_index in completed_segments:
                continue
            step = "segment_cancel_check"
            if _cancel_requested(request.cancel_callback):
                receipt = _mark_terminal(
                    writer,
                    plan,
                    receipt,
                    status="cancelled",
                    error_code="technical_universe_v4_cancelled",
                )
                return _result(
                    status="cancelled",
                    step=step,
                    plan=plan,
                    receipt=receipt,
                    resumed=resumed,
                    calculation_identity_sha256=preflight.calculation_identity_sha256,
                    completed_segments=completed_segments,
                    missing_data_codes=missing_data_codes,
                )

            step = "segment_source_pin_before"
            _assert_current_pins(preflight)
            segment = plan.segment_cohort(segment_index)
            attempt_root = (
                preflight.segment_output_root
                / plan.generation_identity_sha256
                / uuid4().hex
                / f"segment-{segment_index + 1:06d}"
            )
            parent_root = attempt_root / "parent"
            child_output_root = attempt_root / "children"
            _validate_segment_roots(
                parent_root,
                child_output_root,
                research_scope=preflight.research_scope,
            )

            step = "segment_parent_production"
            parent_result = produce_daily_market_technical_parent_v4(
                source_database=preflight.source_database,
                cohort=segment,
                decision_cutoff=plan.source_clock.decision_cutoff,
                child_output_root=child_output_root,
                parent_root=parent_root,
                research_scope=preflight.research_scope,
                cancel_callback=request.cancel_callback,
            )
            if parent_result.status != "complete":
                parent_status: Literal["cancelled", "failed"] = (
                    "cancelled" if parent_result.status == "cancelled" else "failed"
                )
                error_code = parent_result.error_code or (
                    "technical_universe_v4_segment_cancelled"
                    if parent_status == "cancelled"
                    else "technical_universe_v4_segment_parent_failed"
                )
                receipt = _mark_terminal(
                    writer,
                    plan,
                    receipt,
                    status=parent_status,
                    error_code=error_code,
                )
                return _result(
                    status=parent_status,
                    step=step,
                    plan=plan,
                    receipt=receipt,
                    error_code=error_code,
                    resumed=resumed,
                    calculation_identity_sha256=preflight.calculation_identity_sha256,
                    completed_segments=completed_segments,
                    missing_data_codes=missing_data_codes,
                )

            parent_plan, parent_receipt = _require_complete_parent_result(parent_result)
            step = "segment_parent_identity_check"
            segment_missing = _verify_new_parent_calculation_identity(
                parent_plan,
                parent_receipt,
                expected_segment=segment,
                full_plan=plan,
                expected_calculation_identity_sha256=(
                    preflight.calculation_identity_sha256
                ),
            )

            step = "segment_source_pin_after"
            _assert_current_pins(preflight)
            parent_reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
                parent_root,
                parent_plan_identity_sha256=parent_plan.identity_sha256,
                parent_plan_sha256=parent_plan.content_sha256,
                parent_receipt_identity_sha256=parent_receipt.identity_sha256,
                parent_receipt_sha256=parent_receipt.content_sha256,
            )

            step = "segment_store_append"
            if receipt is None:
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_receipt_missing"
                )
            receipt = writer.record_segment_parent(
                plan.generation_identity_sha256,
                plan.identity_sha256,
                receipt.identity_sha256,
                expected_previous_receipt_sha256=receipt.content_sha256,
                segment_index=segment_index,
                parent_reference=parent_reference,
            )
            completed_segments.append(segment_index)
            missing_data_codes.update(segment_missing)

        step = "final_source_pin"
        _assert_current_pins(preflight)
        if receipt is None:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_receipt_missing"
            )
        step = "complete"
        receipt = writer.complete(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            receipt.identity_sha256,
            expected_previous_receipt_sha256=receipt.content_sha256,
        )
        return _result(
            status="complete",
            step=step,
            plan=plan,
            receipt=receipt,
            resumed=resumed,
            calculation_identity_sha256=preflight.calculation_identity_sha256,
            completed_segments=completed_segments,
            missing_data_codes=missing_data_codes,
        )
    except Exception as exc:
        cause_code = _exception_code(exc)
        error_code = (
            exc.code
            if isinstance(exc, DailyMarketTechnicalUniverseV4ProductionError)
            else "technical_universe_v4_production_failed"
        )
        if receipt is not None and receipt.status == "partial":
            try:
                receipt = _mark_terminal(
                    writer,
                    plan,
                    receipt,
                    status="failed",
                    error_code=error_code,
                )
            except Exception:
                # 保留最後已保存的 receipt；結果會帶出實際 failure code。
                pass
        return _result(
            status="failed",
            step=step,
            plan=plan,
            receipt=receipt,
            error_code=error_code,
            cause_code=cause_code,
            resumed=resumed,
            calculation_identity_sha256=preflight.calculation_identity_sha256,
            completed_segments=completed_segments,
            missing_data_codes=missing_data_codes,
        )


def _read_source_clock(
    source_database: Path,
    decision_cutoff: datetime,
) -> DailyMarketTechnicalSourceClockV4:
    if not isinstance(decision_cutoff, datetime) or decision_cutoff.utcoffset() is None:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_decision_cutoff_invalid"
        )
    try:
        with DailyMarketTechnicalReadSession(source_database, decision_cutoff) as session:
            source_clock = session.clock
            if session.loaded_stock_codes:
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_clock_session_loaded_stock_data"
                )
            # 只取得 source clock；明確關閉空 session，不要求載入或發布股票窗口。
            session.close()
        return source_clock
    except DailyMarketTechnicalUniverseV4ProductionError:
        raise
    except Exception as exc:
        cause_code = _exception_code(exc)
        code = (
            cause_code
            if cause_code == "daily_technical_requires_after_close_cutoff"
            else "technical_universe_v4_source_clock_read_failed"
        )
        raise DailyMarketTechnicalUniverseV4ProductionError(
            code,
            cause_code=cause_code,
        ) from exc


def _current_calculation_identity() -> str:
    from app_module import daily_market_technical_source

    try:
        identity, method_version, _talib_version = (
            daily_market_technical_source._calculation_identity()
        )
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_calculation_identity_unavailable",
            cause_code=_exception_code(exc),
        ) from exc
    if (
        not isinstance(identity, str)
        or _SHA256_RE.fullmatch(identity) is None
        or not isinstance(method_version, str)
        or not method_version.strip()
    ):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_calculation_identity_invalid"
        )
    return identity


def _assert_current_pins(preflight: DailyMarketTechnicalUniverseV4Preflight) -> None:
    calculation_before = _current_calculation_identity()
    if calculation_before != preflight.calculation_identity_sha256:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_calculation_identity_changed"
        )
    current_clock = _read_source_clock(
        preflight.source_database,
        preflight.plan.source_clock.decision_cutoff,
    )
    if (
        current_clock.identity_sha256 != preflight.plan.source_clock.identity_sha256
        or current_clock.to_dict() != preflight.plan.source_clock.to_dict()
    ):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_source_clock_changed"
        )
    calculation_after = _current_calculation_identity()
    if calculation_after != preflight.calculation_identity_sha256:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_calculation_identity_changed"
        )


def _verify_new_parent_calculation_identity(
    parent_plan: DailyMarketTechnicalParentPlanV4,
    parent_receipt: DailyMarketTechnicalParentReceiptV4,
    *,
    expected_segment: DailyMarketTechnicalCohortV4,
    full_plan: DailyMarketTechnicalUniverseV4Plan,
    expected_calculation_identity_sha256: str,
) -> tuple[str, ...]:
    payload = parent_plan.to_dict()
    full_payload = full_plan.to_dict()
    if (
        payload.get("cohort") != expected_segment.to_dict()
        or payload.get("source_clock") != full_payload.get("source_clock")
        or payload.get("source_clock_identity_sha256")
        != full_payload.get("source_clock_identity_sha256")
        or payload.get("method_contracts") != full_payload.get("method_contracts")
        or payload.get("method_contracts_sha256")
        != full_payload.get("method_contracts_sha256")
        or parent_receipt.status != "complete"
    ):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_parent_identity_mismatch"
        )
    evidence = payload.get("source_stock_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(
        expected_segment.included_stock_codes
    ):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_parent_source_evidence_invalid"
        )
    missing: list[str] = []
    for expected_code, item in zip(expected_segment.included_stock_codes, evidence):
        if not isinstance(item, Mapping) or item.get("stock_code") != expected_code:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_parent_source_evidence_invalid"
            )
        if item.get("calculation_identity_sha256") != expected_calculation_identity_sha256:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_parent_calculation_identity_mismatch"
            )
        if type(item.get("row_count")) is not int or item["row_count"] < 0:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_parent_source_evidence_invalid"
            )
        if item["row_count"] == 0:
            missing.append(expected_code)
    return tuple(missing)


def _verify_saved_parent_calculation_identities(
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    *,
    expected_calculation_identity_sha256: str,
) -> None:
    for segment_index, reference in state.segment_parent_references:
        try:
            package = read_daily_market_technical_parent_capture_v4(
                reference.parent_root,
                reference.parent_plan_identity_sha256,
                reference.parent_receipt_identity_sha256,
                expected_receipt_sha256=reference.parent_receipt_sha256,
                expected_plan_sha256=reference.parent_plan_sha256,
            )
        except Exception as exc:
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_saved_parent_read_failed",
                cause_code=_exception_code(exc),
            ) from exc
        parent_plan = package.get("plan")
        parent_receipt = package.get("receipt")
        if not isinstance(parent_plan, Mapping) or not isinstance(parent_receipt, Mapping):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_saved_parent_invalid"
            )
        expected_segment = state.plan.segment_cohort(segment_index)
        full_payload = state.plan.to_dict()
        if (
            parent_plan.get("cohort") != expected_segment.to_dict()
            or parent_plan.get("source_clock") != full_payload.get("source_clock")
            or parent_plan.get("source_clock_identity_sha256")
            != full_payload.get("source_clock_identity_sha256")
            or parent_plan.get("method_contracts") != full_payload.get("method_contracts")
            or parent_plan.get("method_contracts_sha256")
            != full_payload.get("method_contracts_sha256")
            or parent_receipt.get("status") != "complete"
        ):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_saved_parent_identity_mismatch"
            )
        evidence = parent_plan.get("source_stock_evidence")
        if not isinstance(evidence, list) or len(evidence) != len(
            expected_segment.included_stock_codes
        ):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_saved_parent_source_evidence_invalid"
            )
        for item in evidence:
            if (
                not isinstance(item, Mapping)
                or item.get("calculation_identity_sha256")
                != expected_calculation_identity_sha256
            ):
                raise DailyMarketTechnicalUniverseV4ProductionError(
                    "technical_universe_v4_saved_parent_calculation_identity_mismatch"
                )


def _require_complete_parent_result(
    result: DailyMarketTechnicalParentV4ProductionResult,
) -> tuple[DailyMarketTechnicalParentPlanV4, DailyMarketTechnicalParentReceiptV4]:
    if (
        result.plan is None
        or result.receipt is None
        or result.plan_identity_sha256 is None
        or result.receipt_identity_sha256 is None
        or result.receipt_content_sha256 is None
        or result.receipt.status != "complete"
    ):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_complete_parent_missing"
        )
    return result.plan, result.receipt


def _mark_terminal(
    writer: DailyMarketTechnicalUniverseV4StoreWriter,
    plan: DailyMarketTechnicalUniverseV4Plan,
    receipt: DailyMarketTechnicalUniverseV4Receipt | None,
    *,
    status: Literal["cancelled", "failed"],
    error_code: str,
) -> DailyMarketTechnicalUniverseV4Receipt:
    if receipt is None:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_terminal_receipt_missing"
        )
    if receipt.status != "partial":
        return receipt
    safe_error = _bounded_error_code(error_code)
    return writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        receipt.identity_sha256,
        expected_previous_receipt_sha256=receipt.content_sha256,
        status=status,
        error_code=safe_error,
    )


def _result(
    *,
    status: Literal["complete", "cancelled", "failed"],
    step: str,
    plan: DailyMarketTechnicalUniverseV4Plan,
    receipt: DailyMarketTechnicalUniverseV4Receipt | None,
    resumed: bool,
    calculation_identity_sha256: str,
    completed_segments: list[int],
    missing_data_codes: set[str],
    error_code: str | None = None,
    cause_code: str | None = None,
) -> DailyMarketTechnicalUniverseV4ProductionResult:
    return DailyMarketTechnicalUniverseV4ProductionResult(
        status=status,
        step=step,
        plan=plan,
        receipt=receipt,
        error_code=error_code,
        cause_code=cause_code,
        resumed=resumed,
        calculation_identity_sha256=calculation_identity_sha256,
        completed_segment_indices=tuple(sorted(set(completed_segments))),
        missing_data_stock_codes=tuple(sorted(missing_data_codes)),
    )


def _failed_result(
    step: str,
    *,
    error_code: str,
    cause_code: str = "",
) -> DailyMarketTechnicalUniverseV4ProductionResult:
    return DailyMarketTechnicalUniverseV4ProductionResult(
        status="failed",
        step=step,
        plan=None,
        receipt=None,
        error_code=error_code,
        cause_code=cause_code or None,
        resumed=False,
        calculation_identity_sha256=None,
        completed_segment_indices=(),
        missing_data_stock_codes=(),
    )


def _canonical_source_database(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_source_path_invalid"
        )
    try:
        canonical = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_source_path_unavailable",
            cause_code=_exception_code(exc),
        ) from exc
    if canonical != raw or not canonical.is_file():
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_source_path_not_canonical"
        )
    return canonical


def _absolute_output_path(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute() or ".." in raw.parts or not raw.name:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_output_path_invalid"
        )
    return raw


def _validate_storage_roots(
    *,
    source_database: Path,
    store_output_root: Path,
    segment_output_root: Path,
    research_scope: ResearchCaptureWriteScope | None,
) -> None:
    if _paths_overlap(store_output_root, segment_output_root):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_store_segment_roots_overlap"
        )
    wal_path = Path(f"{source_database}-wal")
    for root in (store_output_root, segment_output_root):
        if (
            source_database.is_relative_to(root)
            or root.is_relative_to(source_database)
            or wal_path.is_relative_to(root)
            or root.is_relative_to(wal_path)
        ):
            raise DailyMarketTechnicalUniverseV4ProductionError(
                "technical_universe_v4_source_output_overlap"
            )
    try:
        BoundedRuleResearchCaptureWriter(
            segment_output_root / "preflight-parent",
            research_scope=research_scope,
        )
        BoundedRuleResearchCaptureWriter(
            segment_output_root / "preflight-children",
            research_scope=research_scope,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_segment_root_invalid",
            cause_code=_exception_code(exc),
        ) from exc


def _validate_segment_roots(
    parent_root: Path,
    child_output_root: Path,
    *,
    research_scope: ResearchCaptureWriteScope | None,
) -> None:
    try:
        parent_writer = BoundedRuleResearchCaptureWriter(
            parent_root,
            research_scope=research_scope,
        )
        child_writer = BoundedRuleResearchCaptureWriter(
            child_output_root,
            research_scope=research_scope,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_segment_root_invalid",
            cause_code=_exception_code(exc),
        ) from exc
    if _paths_overlap(parent_writer.output_root, child_writer.output_root):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_segment_roots_overlap"
        )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _cancel_requested(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    try:
        result = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_cancel_callback_failed",
            cause_code=_exception_code(exc),
        ) from exc
    if not isinstance(result, bool):
        raise DailyMarketTechnicalUniverseV4ProductionError(
            "technical_universe_v4_cancel_callback_invalid"
        )
    return result


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _bounded_error_code(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "technical_universe_v4_unknown_failure"
    normalized = re.sub(r"[^A-Za-z0-9_.:-]", "_", value.strip())
    return normalized[:_ERROR_CODE_MAX_CHARS] or "technical_universe_v4_unknown_failure"


def _exception_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return _bounded_error_code(code)
    if isinstance(exc, DailyMarketTechnicalUniverseV4ProductionError):
        return _bounded_error_code(exc.code)
    return _bounded_error_code(type(exc).__name__)
