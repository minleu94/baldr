"""唯讀的每日投資決策旅程 read model。

本模組只讀取既有的 DecisionDesk snapshot、排程輸出、EvidenceEvent／Outcome
與隔離 learning receipt。它不執行推薦、forward outcome 計算、策略或任何
資料庫／持倉寫入；Workbench 只消費這個模組投影出的純 DTO。
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from app_module.decision_desk_dtos import DecisionDeskSnapshot
from app_module.evidence_event_dtos import EvidenceEvent, EvidenceOutcome
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjection,
)
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation.persistence import ExecutionPersistenceError
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    canonical_scheduled_decision_date,
    execution_result_config,
    recommendation_runs_dir,
    verified_saved_calibration_projections,
)
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus
from app_module.sqlite_read_only import check_read_cancelled, connect_read_only_sqlite
from app_module.workbench_dtos import (
    WorkbenchDailyEvidence,
    WorkbenchEvidenceWindow,
    WorkbenchJourneyStep,
    WorkbenchLearningReceipt,
    ResearchFallbackPacket,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from app_module.v4_evidence_identity import DEFAULT_RETURN_BASIS


DEFAULT_EVENT_TYPE = "recommendation_included"
DEFAULT_WINDOWS = (5, 10, 20, 60)
DEFAULT_MAX_EVENTS = 2500


@dataclass(frozen=True)
class _CandidateRead:
    status: str = "missing"
    result_id: str | None = None
    source_id: str | None = None
    source_snapshot_id: str | None = None
    data_date: str | None = None
    quality: str = "missing"
    symbols: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    requested_count: int | None = None
    degraded_count: int | None = None
    missing_count: int | None = None
    identity: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PendingHorizonAnchor:
    """可供 revisit 判讀的單一 event／outcome identity 摘要。"""

    horizon_days: int
    decision_date: str
    symbol: str | None = None
    source_id: str | None = None
    source_snapshot_id: str | None = None
    identity: tuple[tuple[str, str], ...] = ()
    window_type: str | None = None
    return_basis: str | None = None


@dataclass(frozen=True)
class _EvidenceRead:
    status: str = "missing"
    event_type: str = DEFAULT_EVENT_TYPE
    scope_start: str | None = None
    scope_end: str | None = None
    require_cohort_identity: bool = True
    event_count: int = 0
    daily_event_count: int = 0
    skipped_incomplete_identity: int = 0
    event_ids: tuple[str, ...] = ()
    source_snapshot_ids: tuple[str, ...] = ()
    outcome_total: int = 0
    outcome_ready: int = 0
    outcome_pending: int = 0
    outcome_missing: int = 0
    windows: tuple[int, ...] = ()
    evidence_windows: tuple[WorkbenchEvidenceWindow, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()
    next_action: str = ""
    matched_source_snapshot_id: str | None = None
    pending_horizon_anchors: tuple[_PendingHorizonAnchor, ...] = ()


class DailyInvestmentJourneyService:
    """Build the Workbench's content-first daily read model without writes."""

    def __init__(
        self,
        config: Any,
        *,
        evidence_db_path: str | Path | None = None,
        trading_calendar: Any | None = None,
        recommendation_queries: Any | None = None,
    ) -> None:
        self.config = config
        self.output_root = Path(config.output_root).resolve()
        self.evidence_db_path = (
            Path(evidence_db_path).resolve()
            if evidence_db_path is not None
            else Path(config.db_file).resolve()
        )
        self.trading_calendar = (
            trading_calendar
            if trading_calendar is not None
            else OfficialTradingCalendar(db_path=getattr(config, "db_file", None))
        )
        self._injected_recommendation_queries = recommendation_queries
        self.recommendation_queries = (
            recommendation_queries
            if recommendation_queries is not None
            else build_recommendation_execution_queries(config)
        )

    def build(
        self,
        *,
        decision_snapshot: DecisionDeskSnapshot | None,
        scheduled_status: ScheduledEvidenceStatus,
        recommendation_learning_status: Mapping[str, Any] | None,
        recommendation_learning_projection: RecommendationLearningEvidenceProjection | None = None,
        requested_decision_date: str | None = None,
    ) -> WorkbenchDailyEvidence:
        decision_date = _date_key(
            requested_decision_date
            or (decision_snapshot.as_of_date.isoformat() if decision_snapshot is not None else None)
        ) or "unknown"
        diagnostics: list[str] = []
        warnings: list[str] = []

        candidate = self._read_candidate(
            requested_date=decision_date,
            scheduled_status=scheduled_status,
        )
        evidence = self._read_evidence(
            requested_date=decision_date,
            candidate=candidate,
            scheduled_status=scheduled_status,
        )
        learning = _project_learning_receipt(
            recommendation_learning_status,
            requested_date=decision_date,
        )

        diagnostics.extend(candidate.diagnostics)
        diagnostics.extend(evidence.diagnostics)
        warnings.extend(candidate.warnings)
        warnings.extend(evidence.warnings)
        if learning is not None:
            diagnostics.extend(learning.diagnostics)
        if recommendation_learning_projection is not None:
            diagnostics.extend(recommendation_learning_projection.diagnostics)

        if decision_snapshot is None:
            diagnostics.append("decision_snapshot_missing")
            warnings.append("市場／產業／持倉摘要缺少 DecisionDeskSnapshot")

        self._check_candidate_event_identity(candidate, evidence, diagnostics, warnings)
        self._check_wrapper_receipt_counts(scheduled_status, evidence, diagnostics, warnings)

        market_summary, industry_summary, stock_summary, watchlist_summary, portfolio_summary = (
            self._snapshot_summaries(decision_snapshot, candidate)
        )
        journey_steps = self._journey_steps(
            decision_date=decision_date,
            decision_snapshot=decision_snapshot,
            candidate=candidate,
            evidence=evidence,
            learning=learning,
        )

        status = _overall_status(
            decision_snapshot=decision_snapshot,
            scheduled_status=scheduled_status,
            candidate=candidate,
            evidence=evidence,
            diagnostics=diagnostics,
        )
        data_as_of_date = candidate.data_date or (
            decision_snapshot.as_of_date.isoformat() if decision_snapshot is not None else None
        )
        learning_summary = _learning_summary(learning)
        candidate_summary = (
            f"{candidate.result_id or '無 result_id'}；{candidate.quality}；"
            f"{candidate.status}"
            if candidate.result_id
            else "候選來源缺失；不能把缺資料解讀為沒有候選"
        )
        evidence_summary = _evidence_summary(evidence)
        headline = _headline(
            decision_date=decision_date,
            decision_snapshot=decision_snapshot,
            candidate=candidate,
            evidence=evidence,
            learning=learning,
            status=status,
        )
        next_action = evidence.next_action or _next_action(
            status=status,
            candidate=candidate,
            evidence=evidence,
            scheduled_status=scheduled_status,
        )
        research_fallback = self._build_research_fallback_packet(
            decision_date=decision_date,
            candidate=candidate,
            evidence=evidence,
            recommendation_learning_projection=recommendation_learning_projection,
        )
        if learning is not None and learning.active_pointer_status == "rule_only":
            warnings.append("目前 active pointer 為 rule_only；沒有 active model，不可稱為 current champion")
        if learning is not None and learning.natural_matured_sample_count == 0:
            warnings.append("隔離 learning receipt 尚無 natural matured sample；不與正式 evidence outcome 混算")
        if recommendation_learning_projection is not None:
            if recommendation_learning_projection.status == "blocked_provenance":
                warnings.append("learning evidence provenance 未通過；Workbench 不顯示 reliability")
            elif recommendation_learning_projection.verified_lane is None:
                warnings.append("learning projection 尚無 typed verified natural evidence；80% 可靠度未知")

        source_trace = _source_trace(
            decision_snapshot=decision_snapshot,
            candidate=candidate,
            evidence=evidence,
            learning=learning,
        )
        if candidate_summary:
            diagnostics.append(f"candidate_summary={candidate_summary}")
        if evidence_summary:
            diagnostics.append(f"evidence_summary={evidence_summary}")
        if learning_summary:
            diagnostics.append(f"learning_summary={learning_summary}")
        if research_fallback is not None:
            diagnostics.append(f"research_fallback_status={research_fallback.status}")

        return WorkbenchDailyEvidence(
            status=status,
            decision_date=decision_date,
            data_as_of_date=data_as_of_date,
            headline=headline,
            next_action=next_action,
            market_summary=market_summary,
            industry_summary=industry_summary,
            stock_summary=stock_summary,
            watchlist_summary=watchlist_summary,
            portfolio_summary=portfolio_summary,
            candidate_symbols=candidate.symbols,
            candidate_count=len(candidate.symbols),
            candidate_status=candidate.status,
            candidate_result_id=candidate.result_id,
            candidate_source_id=candidate.source_id,
            candidate_source_snapshot_id=candidate.source_snapshot_id,
            candidate_data_date=candidate.data_date,
            candidate_quality=candidate.quality,
            candidate_requested_count=candidate.requested_count,
            candidate_degraded_count=candidate.degraded_count,
            candidate_missing_count=candidate.missing_count,
            candidate_reasons=candidate.reasons,
            candidate_identity=candidate.identity,
            evidence_event_type=evidence.event_type,
            evidence_scope_start=evidence.scope_start,
            evidence_scope_end=evidence.scope_end,
            evidence_require_cohort_identity=evidence.require_cohort_identity,
            evidence_event_count=evidence.event_count,
            evidence_daily_event_count=evidence.daily_event_count,
            evidence_skipped_incomplete_identity=evidence.skipped_incomplete_identity,
            evidence_event_ids=evidence.event_ids,
            evidence_source_snapshot_ids=evidence.source_snapshot_ids,
            outcome_total=evidence.outcome_total,
            outcome_ready=evidence.outcome_ready,
            outcome_pending=evidence.outcome_pending,
            outcome_missing=evidence.outcome_missing,
            outcome_windows=evidence.windows,
            evidence_windows=evidence.evidence_windows,
            learning=learning,
            learning_projection=recommendation_learning_projection,
            research_fallback=research_fallback,
            journey_steps=journey_steps,
            warnings=tuple(dict.fromkeys(warnings)),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            source_trace=source_trace,
        )

    def _build_research_fallback_packet(
        self,
        *,
        decision_date: str,
        candidate: _CandidateRead,
        evidence: _EvidenceRead,
        recommendation_learning_projection: RecommendationLearningEvidenceProjection | None,
    ) -> ResearchFallbackPacket | None:
        """由既有 read model 組合受界定的研究交接 packet。

        packet 不持久化，也沒有 action callback；只說明目前缺口、研究問題與
        下一個安全的唯讀檢查。特別不把 score、receipt 宣稱或 historical
        evaluation 當成 natural probability authority。
        """

        projection = recommendation_learning_projection
        lane = _fallback_lane(projection)
        evidence_reason = _evidence_fallback_reason(evidence)
        candidate_reason = _candidate_fallback_reason(candidate)
        source_trace = tuple(
            dict.fromkeys(
                (
                    *candidate.source_trace,
                    *evidence.source_trace,
                    *(projection.source_trace if projection is not None else ()),
                )
            )
        )
        cost_lane = projection.cost_lane if projection is not None else "unknown"
        natural_status = _fallback_natural_status(projection, evidence)
        status = _fallback_status(
            candidate=candidate,
            evidence=evidence,
            projection=projection,
        )
        if status == "not_needed":
            return None
        missing_reason = _fallback_missing_reason(
            status=status,
            candidate=candidate,
            evidence=evidence,
            projection=projection,
            candidate_reason=candidate_reason,
            evidence_reason=evidence_reason,
            lane=lane,
        )
        research_question = _fallback_research_question(
            status=status,
            candidate=candidate,
            evidence=evidence,
            projection=projection,
        )
        next_step = _fallback_next_step(
            status=status,
            candidate=candidate,
            evidence=evidence,
            projection=projection,
            lane=lane,
        )
        historical_research_allowed = bool(
            projection is not None
            and projection.historical_evaluation_sample_count > 0
        )
        limitations = _fallback_limitations(
            projection=projection,
            historical_research_allowed=historical_research_allowed,
        )
        revisit_date, revisit_status, revisit_basis, revisit_reason = _fallback_revisit(
            status=status,
            decision_date=decision_date,
            candidate=candidate,
            evidence=evidence,
            projection=projection,
            calendar=self.trading_calendar,
        )
        if historical_research_allowed:
            next_step = (
                f"{next_step}；若要比較，可另看 historical replay，不能把它當 natural evidence。"
            )
        return ResearchFallbackPacket(
            status=status,
            scope_result_id=candidate.result_id,
            scope_stock_codes=candidate.symbols,
            decision_date=None if decision_date == "unknown" else decision_date,
            cost_lane=cost_lane,
            source_id=candidate.source_id,
            source_snapshot_id=candidate.source_snapshot_id or evidence.matched_source_snapshot_id,
            source_owner="未知（既有來源未提供 owner）",
            source_owner_known=False,
            missing_reason=missing_reason,
            research_question=research_question,
            next_step=next_step,
            revisit_date=revisit_date,
            revisit_status=revisit_status,
            revisit_basis=revisit_basis,
            revisit_reason=revisit_reason,
            natural_evidence_status=natural_status,
            limitations=limitations,
            historical_research_allowed=historical_research_allowed,
            positive_fallback_allowed=False,
            read_only=True,
            write_intent=False,
            source_trace=source_trace,
        )

    def _read_candidate(
        self,
        *,
        requested_date: str,
        scheduled_status: ScheduledEvidenceStatus,
    ) -> _CandidateRead:
        diagnostics: list[str] = []
        warnings: list[str] = []
        status_path = self.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
        payload = _read_json_object(status_path, diagnostics, "recommendation_snapshot")
        if payload is None:
            return _CandidateRead(
                status="missing" if status_path.exists() is False else "read_failure",
                warnings=("每日 recommendation snapshot 狀態缺失／無法讀取",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"recommendation_snapshot.status_path={status_path}",),
            )

        result_id = _text(payload.get("result_id")) or _text(scheduled_status.recommendation_result_id)
        payload_date = _date_key(payload.get("decision_date")) or _date_key(scheduled_status.decision_date)
        if payload_date and requested_date != "unknown" and payload_date != requested_date:
            if payload_date > requested_date:
                diagnostics.append(
                    f"recommendation_snapshot_future_date:{payload_date}:requested={requested_date}"
                )
                return _CandidateRead(
                    status="future_blocked",
                    result_id=result_id,
                    data_date=_date_key(payload.get("data_as_of_date")),
                    quality="degraded",
                    warnings=("推薦 snapshot 日期晚於決策日，已阻擋使用",),
                    diagnostics=tuple(diagnostics),
                    source_trace=(
                        f"recommendation_snapshot.result_id={result_id or 'unknown'}",
                        f"recommendation_snapshot.decision_date={payload_date}",
                    ),
                )
            diagnostics.append(
                f"recommendation_snapshot_stale_date:{payload_date}:requested={requested_date}"
            )
            warnings.append("推薦 snapshot 不是目前決策日，候選只保留為 stale 參考")

        cohort = _mapping(payload.get("snapshot_cohort"))
        rows: tuple[Mapping[str, Any], ...] = ()
        run_payload: Mapping[str, Any] | None = None
        run_context: Mapping[str, Any] = {}
        saved_read: RecommendationExecutionReadModel | None = None
        legacy_original_payload: Any | None = None
        legacy_projection_accepted = False
        legacy_identity_conflict = False
        if result_id:
            runs_dir_raw = _text(payload.get("runs_dir"))
            runs_dir = recommendation_runs_dir(self.config)
            if runs_dir_raw:
                safe_runs_dir = _safe_output_path(self.output_root, Path(runs_dir_raw))
                if safe_runs_dir is None:
                    diagnostics.append("recommendation_snapshot_runs_dir_outside_output_root")
                else:
                    runs_dir = safe_runs_dir
            if not runs_dir_raw or _safe_output_path(self.output_root, runs_dir) is not None:
                queries = self._queries_for_runs_dir(runs_dir)
                try:
                    saved_read = queries.get(result_id)
                    if saved_read is None or saved_read.legacy_result is not None:
                        legacy_original_payload = queries.get_legacy_original_payload(
                            result_id,
                            allow_unindexed_legacy=True,
                        )
                except (ExecutionPersistenceError, ValueError) as exc:
                    diagnostics.append(
                        f"recommendation_run_query_failure:{type(exc).__name__}"
                    )
                    saved_read = None
                    legacy_original_payload = None
            else:
                saved_read = None
            if saved_read is None and legacy_original_payload is None and not any(
                item.startswith("recommendation_run_query_failure:")
                or item == "recommendation_snapshot_runs_dir_outside_output_root"
                for item in diagnostics
            ):
                diagnostics.append(f"recommendation_run_missing:{result_id}")
        if saved_read is not None:
            if saved_read.result_id != result_id:
                diagnostics.append(
                    f"recommendation_run_result_id_mismatch:{saved_read.result_id}!={result_id}"
                )
                saved_read = None
            elif saved_read.execution is not None:
                execution = saved_read.execution
                result_config = execution_result_config(execution)
                if result_config.get("scheduled_snapshot") is True:
                    canonical_decision_date = canonical_scheduled_decision_date(saved_read)
                    if canonical_decision_date is None:
                        diagnostics.append("recommendation_scheduled_decision_date_invalid")
                        saved_read = None
                    elif payload_date is None:
                        diagnostics.append("recommendation_scheduled_status_decision_date_missing")
                        saved_read = None
                    elif canonical_decision_date != payload_date:
                        diagnostics.append(
                            "recommendation_scheduled_decision_date_mismatch:"
                            f"{canonical_decision_date}!={payload_date}"
                        )
                        saved_read = None
                else:
                    selected_date = execution.context.as_of_date or execution.request.as_of_date
                    if (
                        selected_date is not None
                        and payload_date is not None
                        and selected_date.isoformat() != payload_date
                    ):
                        diagnostics.append(
                            "recommendation_execution_as_of_mismatch:"
                            f"{selected_date.isoformat()}!={payload_date}"
                        )
                        saved_read = None
                if saved_read is not None and (
                    execution.status is not ExecutionStatus.COMPLETED
                    or execution.decision is None
                ):
                    diagnostics.append(
                        f"recommendation_execution_unsupported:{execution.status.value}"
                    )
                    saved_read = None
                elif saved_read is not None:
                    execution_cohort = _canonical_cohort(saved_read)
                    if execution_cohort:
                        status_cohort_hash = _text(cohort.get("cohort_hash"))
                        execution_cohort_hash = _text(execution_cohort.get("cohort_hash"))
                        if (
                            status_cohort_hash
                            and execution_cohort_hash
                            and status_cohort_hash != execution_cohort_hash
                        ):
                            diagnostics.append("recommendation_execution_cohort_mismatch")
                            saved_read = None
                        else:
                            cohort = cohort or execution_cohort
                    if saved_read is not None:
                        canonical_rows, canonical_context = _canonical_candidate_rows(saved_read)
                        identity_mismatch = _canonical_identity_mismatch(
                            payload,
                            cohort,
                            canonical_context,
                        )
                        if identity_mismatch:
                            diagnostics.append(
                                f"recommendation_execution_identity_mismatch:{identity_mismatch}"
                            )
                            saved_read = None
                        else:
                            rows = canonical_rows
                            run_context = canonical_context
                            run_payload = {"result_id": result_id}
            elif saved_read.legacy_result is not None:
                legacy = saved_read.legacy_result
                if legacy_original_payload is None:
                    diagnostics.append("recommendation_run_legacy_original_payload_missing")
                    saved_read = None
                elif not _legacy_read_view_matches_projection(
                    saved_read,
                    legacy_original_payload,
                ):
                    diagnostics.append("recommendation_run_legacy_payload_read_mismatch")
                    saved_read = None
                elif (
                    legacy_original_payload.result_id != result_id
                    or legacy_original_payload.payload.get("result_id") != result_id
                ):
                    diagnostics.append("recommendation_run_legacy_original_payload_identity_mismatch")
                    saved_read = None
                else:
                    exact_payload = legacy_original_payload.payload
                    identity_mismatch = _legacy_identity_mismatch(payload, exact_payload)
                    if identity_mismatch:
                        diagnostics.append(
                            f"recommendation_legacy_identity_mismatch:{identity_mismatch}"
                        )
                        legacy_identity_conflict = True
                        saved_read = None
                    else:
                        legacy_projection_accepted = True
                        rows, row_diagnostic = _legacy_payload_candidate_rows(exact_payload)
                        if row_diagnostic:
                            diagnostics.append(row_diagnostic)
                        run_context = _mapping(exact_payload.get("run_context")) or _mapping(legacy.run_context)
                        run_payload = exact_payload
            else:
                diagnostics.append("recommendation_run_read_view_unsupported")
                saved_read = None
        elif legacy_original_payload is not None:
            if (
                legacy_original_payload.source != "unindexed_legacy_file"
                or
                legacy_original_payload.result_id != result_id
                or legacy_original_payload.payload.get("result_id") != result_id
            ):
                diagnostics.append("recommendation_run_legacy_original_payload_identity_mismatch")
            else:
                exact_payload = legacy_original_payload.payload
                identity_mismatch = _legacy_identity_mismatch(payload, exact_payload)
                if identity_mismatch:
                    diagnostics.append(
                        f"recommendation_legacy_identity_mismatch:{identity_mismatch}"
                    )
                    legacy_identity_conflict = True
                else:
                    rows, row_diagnostic = _legacy_payload_candidate_rows(exact_payload)
                    if row_diagnostic:
                        diagnostics.append(row_diagnostic)
                    legacy_projection_accepted = True
                    run_context = _mapping(exact_payload.get("run_context"))
                    run_payload = exact_payload
        symbols = tuple(
            dict.fromkeys(
                code
                for row in rows
                for code in (_text(row.get("stock_code")) or _text(row.get("證券代號")),)
                if code
            )
        )
        reasons = tuple(_candidate_reason(row) for row in rows if _candidate_reason(row))
        requested_count = _first_int(
            (cohort, "requested_count"),
            (cohort, "requested_symbols"),
            (payload, "requested_count"),
        )
        degraded_count = _first_int(
            (cohort, "degraded_symbols"),
            (cohort, "degraded_count"),
            (payload, "degraded_symbols"),
        )
        missing_count = _first_int(
            (cohort, "missing_symbols"),
            (cohort, "missing_count"),
            (payload, "missing_symbols"),
        )
        coverage_status = _text(cohort.get("coverage_status")) or ""
        has_degraded_symbols = degraded_count is not None and degraded_count > 0
        has_missing_symbols = missing_count is not None and missing_count > 0
        quality = (
            "degraded"
            if coverage_status == "degraded" or has_degraded_symbols or has_missing_symbols
            else "observed"
        )
        if not rows and _int_or_none(payload.get("recommendations_count")):
            diagnostics.append("recommendation_snapshot_rows_missing_but_count_nonzero")
            warnings.append("推薦 snapshot 宣稱有候選，但 verified saved result 未提供候選列")
        if not result_id:
            diagnostics.append("recommendation_snapshot_result_id_missing")
        if result_id and not rows:
            status = "degraded" if diagnostics else "missing"
        elif payload_date and requested_date != "unknown" and payload_date != requested_date:
            status = "stale"
        elif quality == "degraded":
            status = "candidate_degraded"
        elif rows:
            status = "candidate"
        else:
            status = "missing"

        data_date = _date_key(
            run_context.get("data_as_of_date")
            or run_context.get("data_date")
            or run_context.get("payload_date")
            or _mapping(run_payload).get("data_as_of_date")
            or _mapping(run_payload).get("data_date")
            or _mapping(run_payload).get("payload_date")
            or payload.get("data_as_of_date")
            or payload.get("data_date")
            or payload.get("payload_date")
            or run_context.get("as_of_date")
            or payload_date
        )
        identity_payload = {} if legacy_identity_conflict else payload
        identity_cohort = {} if legacy_identity_conflict else cohort
        identity = _candidate_identity(
            identity_payload, identity_cohort, run_payload, run_context
        )
        source_snapshot_id: str | None = _text(identity_payload.get("source_snapshot_id"))
        source_snapshot_id = (
            source_snapshot_id
            or _text(_mapping(run_payload).get("source_snapshot_id"))
            or _text(identity_cohort.get("universe_snapshot_id"))
        )
        source_id: str | None = (
            _text(identity_payload.get("source_id"))
            or _text(_mapping(run_payload).get("source_id"))
            or result_id
        )
        if legacy_identity_conflict:
            source_id = None
            source_snapshot_id = None
        trace = [
            f"recommendation_snapshot.result_id={result_id or 'unknown'}",
            f"recommendation_snapshot.decision_date={payload_date or 'unknown'}",
            f"recommendation_snapshot.status={_text(payload.get('status')) or 'unknown'}",
        ]
        if cohort.get("cohort_hash"):
            trace.append(f"recommendation_snapshot.cohort_hash={_text(cohort.get('cohort_hash'))}")
        if saved_read is not None:
            trace.append(f"recommendation_run.result_id={saved_read.result_id}")
            trace.append(f"recommendation_run.integrity_basis={saved_read.integrity_basis}")
            if saved_read.raw_artifact_sha256:
                trace.append(f"recommendation_run.raw_artifact_sha256={saved_read.raw_artifact_sha256}")
            if saved_read.execution is not None:
                trace.append("recommendation_run.format=RecommendationExecution")
        elif legacy_original_payload is not None and legacy_projection_accepted:
            trace.append(f"recommendation_run.result_id={legacy_original_payload.result_id}")
            trace.append(
                "recommendation_run.integrity_basis="
                f"{legacy_original_payload.integrity_basis}"
            )
            trace.append(
                "recommendation_run.original_payload_source="
                f"{legacy_original_payload.source}"
            )
            trace.append(
                "recommendation_run.raw_artifact_sha256="
                f"{legacy_original_payload.raw_artifact_sha256}"
            )
        legacy_source_snapshot_hash = _text(
            _mapping(run_payload).get("source_snapshot_hash")
        )
        if legacy_source_snapshot_hash:
            trace.append(
                f"recommendation_run.source_snapshot_hash={legacy_source_snapshot_hash}"
            )
        calibration_by_code = (
            verified_saved_calibration_projections(saved_read)
            if saved_read is not None and saved_read.execution is not None
            else {}
        )
        for row in rows[:20]:
            code = _text(row.get("stock_code")) or _text(row.get("證券代號")) or "unknown"
            ranking_method = _text(row.get("ranking_method"))
            if ranking_method:
                trace.append(f"recommendation_candidate[{code}].ranking_method={ranking_method}")
            recommendation_rank = row.get("recommendation_rank")
            if isinstance(recommendation_rank, int) and not isinstance(
                recommendation_rank, bool
            ):
                trace.append(
                    f"recommendation_candidate[{code}].recommendation_rank={recommendation_rank}"
                )
            calibration = calibration_by_code.get(code)
            calibration_status = (
                calibration.calibrated_probability_status
                if calibration is not None
                else _text(row.get("calibrated_probability_status"))
            )
            if calibration_status:
                trace.append(
                    f"recommendation_candidate[{code}].calibrated_probability_status={calibration_status}"
                )
        return _CandidateRead(
            status=status,
            result_id=result_id,
            source_id=source_id,
            source_snapshot_id=source_snapshot_id,
            data_date=data_date,
            quality=quality,
            symbols=symbols,
            reasons=reasons[:20],
            requested_count=requested_count,
            degraded_count=degraded_count,
            missing_count=missing_count,
            identity=identity,
            warnings=tuple(warnings),
            diagnostics=tuple(diagnostics),
            source_trace=tuple(trace),
        )

    def _queries_for_runs_dir(self, runs_dir: Path) -> Any:
        """依 wrapper 已保存且通過 output-root 邊界的 runs_dir 取得 query view。"""

        configured_runs_dir = recommendation_runs_dir(self.config).resolve()
        if self._injected_recommendation_queries is not None or runs_dir.resolve() == configured_runs_dir:
            return self.recommendation_queries
        return build_recommendation_execution_queries(self.config, runs_dir=runs_dir)


    def _read_evidence(
        self,
        *,
        requested_date: str,
        candidate: _CandidateRead,
        scheduled_status: ScheduledEvidenceStatus,
    ) -> _EvidenceRead:
        diagnostics: list[str] = []
        warnings: list[str] = []
        status_path = self.output_root / "scheduled" / "forward_outcomes" / "latest_status.json"
        payload = _read_json_object(status_path, diagnostics, "forward_outcomes")
        if payload is None:
            if not self.evidence_db_path.exists():
                diagnostics.append(f"evidence_db_missing:{self.evidence_db_path}")
            return _EvidenceRead(
                status="missing" if not status_path.exists() else "read_failure",
                scope_start=requested_date if requested_date != "unknown" else None,
                scope_end=requested_date if requested_date != "unknown" else None,
                warnings=("forward outcome scope receipt 缺失／無法讀取",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"forward_outcomes.status_path={status_path}",),
            )

        event_type = _text(payload.get("event_type")) or DEFAULT_EVENT_TYPE
        if event_type != DEFAULT_EVENT_TYPE:
            diagnostics.append(f"forward_outcomes_event_type_unsupported:{event_type}")
            return _EvidenceRead(
                status="read_failure",
                event_type=event_type,
                warnings=("forward outcome receipt 不是 recommendation_included scope",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"forward_outcomes.event_type={event_type}",),
            )
        scope_start = _date_key(payload.get("start_date")) or _date_key(payload.get("scope_start"))
        scope_end = _date_key(payload.get("end_date")) or _date_key(payload.get("scope_end"))
        if not scope_start or not scope_end:
            scope_start = scope_start or requested_date
            scope_end = scope_end or requested_date
            diagnostics.append("forward_outcomes_scope_missing")
            warnings.append("forward outcome receipt 沒有完整日期範圍；只以決策日讀取")
        require_identity = _bool_or_default(payload.get("require_cohort_identity"), True)
        windows = _positive_ints(
            payload.get("outcome_windows")
            or payload.get("windows")
            or _mapping(payload.get("config")).get("outcome_windows")
            or DEFAULT_WINDOWS
        )
        max_events = _int_or_default(payload.get("max_events"), DEFAULT_MAX_EVENTS)
        if max_events <= 0:
            max_events = DEFAULT_MAX_EVENTS

        if not self.evidence_db_path.exists():
            diagnostics.append(f"evidence_db_missing:{self.evidence_db_path}")
            return _EvidenceRead(
                status="missing",
                event_type=event_type,
                scope_start=scope_start,
                scope_end=scope_end,
                require_cohort_identity=require_identity,
                windows=windows,
                warnings=("正式 Evidence DB 不存在；沒有把缺資料當成零事件",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"evidence_db={self.evidence_db_path}",),
            )
        if not _sqlite_table_exists(self.evidence_db_path, "evidence_events", diagnostics):
            return _EvidenceRead(
                status="missing",
                event_type=event_type,
                scope_start=scope_start,
                scope_end=scope_end,
                require_cohort_identity=require_identity,
                windows=windows,
                warnings=("正式 EvidenceEvent table 不存在；無法判定成熟度",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"evidence_db={self.evidence_db_path}",),
            )

        try:
            repository = EvidenceEventRepository(self.config, db_path=self.evidence_db_path)
            events = repository.list_events(
                event_type=event_type,
                start_date=scope_start,
                end_date=scope_end,
                limit=max_events,
                complete_cohort_identity_only=require_identity,
                outcome_windows=windows,
                incomplete_outcomes_first=True,
            )
            daily_events = repository.list_events(
                event_type=event_type,
                decision_date=requested_date if requested_date != "unknown" else None,
                limit=max_events,
                complete_cohort_identity_only=require_identity,
                outcome_windows=windows,
                incomplete_outcomes_first=True,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            diagnostics.append(f"evidence_read_failure:{type(exc).__name__}:{exc}")
            return _EvidenceRead(
                status="read_failure",
                event_type=event_type,
                scope_start=scope_start,
                scope_end=scope_end,
                require_cohort_identity=require_identity,
                windows=windows,
                warnings=("EvidenceEvent 唯讀查詢失敗；未重算或補寫 outcome",),
                diagnostics=tuple(diagnostics),
                source_trace=(f"evidence_db={self.evidence_db_path}",),
            )

        outcomes: list[EvidenceOutcome] = []
        for event in events:
            try:
                outcomes.extend(repository.list_outcomes(event_id=event.event_id))
            except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
                diagnostics.append(f"evidence_outcome_read_failure:{event.event_id}:{type(exc).__name__}")
        windows_summary = _summarize_outcomes(events, outcomes, windows)
        matched_source_snapshot_id = _matched_source_snapshot_id(events, candidate)
        pending_horizon_anchors = _pending_horizon_anchors(
            events,
            outcomes,
            windows,
            requested_date=requested_date,
        )
        total = sum(item.total for item in windows_summary)
        ready = sum(item.ready for item in windows_summary)
        pending = sum(item.pending for item in windows_summary)
        missing = sum(item.missing for item in windows_summary)
        skipped = _first_int(
            (_mapping(payload.get("health")), "events_skipped_incomplete_identity"),
            (_mapping(payload.get("summary")), "events_skipped_incomplete_identity"),
        )
        if skipped is None:
            skipped = scheduled_status.forward_health_events_skipped_incomplete_identity or 0
        if events and pending == total:
            evidence_status = "waiting_for_time"
            next_action = "等待下一個官方交易日的可見價格觀測；成熟前不回填、不補未來資料。"
        elif events and ready == total and total > 0:
            evidence_status = "ready"
            next_action = "可在 Evidence 頁逐 horizon 檢視已成熟結果；不把 outcome 擴張成交易指令。"
        elif events:
            evidence_status = "degraded"
            next_action = "先檢視 Evidence scope、identity 與各 horizon 缺口，再決定是否等待或修復來源。"
        else:
            evidence_status = "missing"
            next_action = "先確認 forward outcome producer 的 scope receipt 與 recommendation event identity。"
        if skipped:
            warnings.append(
                f"完整 cohort identity 的 {event_type} 事件 {len(events)} 筆；另有 {skipped} 筆不完整 identity 被跳過"
            )
        event_ids = tuple(str(event.event_id) for event in events)
        source_snapshot_ids = tuple(
            dict.fromkeys(
                str(value)
                for event in events
                for value in (event.source_snapshot_id,)
                if str(value or "").strip()
            )
        )
        receipt_summary = _mapping(payload.get("summary"))
        receipt_scanned = _int_or_none(receipt_summary.get("events_scanned"))
        if receipt_scanned is not None and receipt_scanned != len(events):
            diagnostics.append(f"forward_outcomes_event_count_mismatch:{len(events)}!={receipt_scanned}")
            warnings.append("forward receipt 與同 scope 唯讀 event count 不一致，狀態降級")
        receipt_outcomes = _int_or_none(receipt_summary.get("outcomes_written"))
        if receipt_outcomes is not None and receipt_outcomes != total:
            diagnostics.append(f"forward_outcomes_outcome_count_mismatch:{total}!={receipt_outcomes}")
        source_trace = [
            f"forward_outcomes.event_type={event_type}",
            f"forward_outcomes.scope={scope_start}..{scope_end}",
            f"forward_outcomes.require_cohort_identity={require_identity}",
            f"forward_outcomes.max_events={max_events}",
        ]
        source_trace.extend(
            f"evidence_event[{event.event_id}].event_hash={event.event_hash}"
            for event in events[:20]
        )
        source_trace.extend(
            f"evidence_event[{event.event_id}].source_snapshot_id={event.source_snapshot_id}"
            for event in events[:20]
        )
        return _EvidenceRead(
            status=evidence_status,
            event_type=event_type,
            scope_start=scope_start,
            scope_end=scope_end,
            require_cohort_identity=require_identity,
            event_count=len(events),
            daily_event_count=len(daily_events),
            skipped_incomplete_identity=skipped,
            event_ids=event_ids,
            source_snapshot_ids=source_snapshot_ids,
            outcome_total=total,
            outcome_ready=ready,
            outcome_pending=pending,
            outcome_missing=missing,
            windows=windows,
            evidence_windows=windows_summary,
            warnings=tuple(warnings),
            diagnostics=tuple(diagnostics),
            source_trace=tuple(source_trace),
            next_action=next_action,
            matched_source_snapshot_id=matched_source_snapshot_id,
            pending_horizon_anchors=pending_horizon_anchors,
        )

    @staticmethod
    def _snapshot_summaries(
        snapshot: DecisionDeskSnapshot | None,
        candidate: _CandidateRead,
    ) -> tuple[str, str, str, str, str]:
        if snapshot is None:
            return (
                "市場：缺少 DecisionDeskSnapshot；不能判定今日市場狀態。",
                "產業：缺少 DecisionDeskSnapshot；不能判定領先／落後。",
                "個股：缺少市場快照或每日候選；請先檢查來源。",
                "觀察清單：缺少市場快照；不自行新增候選。",
                "持倉：缺少市場快照；不自行推定沒有風險。",
            )
        regime = snapshot.market_regime
        breadth = snapshot.market_breadth
        rotation = snapshot.sector_rotation
        watchlist = snapshot.watchlist_triggers
        portfolio = snapshot.portfolio_alerts
        market = (
            f"市場：{regime.regime_label or '未知'}｜廣度上漲 {breadth.advancing if breadth.advancing is not None else '未知'}、"
            f"下跌 {breadth.declining if breadth.declining is not None else '未知'}、"
            f"平盤 {breadth.unchanged if breadth.unchanged is not None else '未知'}｜"
            f"資料日 {snapshot.as_of_date.isoformat()}｜品質 {_quality_label(snapshot.overall_quality)}"
        )
        industry = _industry_rotation_summary(rotation)
        if candidate.reasons:
            stock = "個股研究候選：" + "；".join(candidate.reasons[:5])
        elif snapshot.stock_focus and snapshot.stock_focus.priority_stocks:
            stock = "個股焦點：" + "；".join(
                f"{item.stock_code} {item.stock_name}（{item.reason}）"
                for item in snapshot.stock_focus.priority_stocks[:5]
            )
        else:
            stock = "個股研究候選：目前沒有可安全呈現的列；空結果不等於通過。"
        watchlist_codes = ", ".join(watchlist.triggered_codes[:8]) or "無"
        watchlist_summary = (
            f"觀察清單：觸發 {watchlist.trigger_count if watchlist.trigger_count is not None else '未知'} 檔"
            f"（{watchlist_codes}）｜品質 {_quality_label(watchlist.quality)}"
        )
        portfolio_codes = ", ".join(portfolio.alert_codes[:8]) or "無"
        portfolio_summary = (
            f"保存快照警示：{portfolio.alert_count if portfolio.alert_count is not None else '未知'} 檔"
            f"（{portfolio_codes}）｜快照資料日 {snapshot.as_of_date.isoformat()}"
            f"｜來源 DecisionDeskSnapshot.portfolio_alerts｜層級 {portfolio.alert_level or '未知'}"
            f"｜品質 {_quality_label(portfolio.quality)}｜不是目前持倉狀態"
        )
        return market, industry, stock, watchlist_summary, portfolio_summary

    @staticmethod
    def _journey_steps(
        *,
        decision_date: str,
        decision_snapshot: DecisionDeskSnapshot | None,
        candidate: _CandidateRead,
        evidence: _EvidenceRead,
        learning: WorkbenchLearningReceipt | None,
    ) -> tuple[WorkbenchJourneyStep, ...]:
        if decision_snapshot is None:
            return (
                WorkbenchJourneyStep(
                    "market",
                    "市場總覽",
                    "missing",
                    "缺少 DecisionDeskSnapshot；不能判讀市場或產業。",
                    "DecisionDeskSnapshot",
                    "先檢查數據更新",
                ),
            )
        candidate_status = "machine_degraded" if candidate.status in {"candidate_degraded", "degraded"} else (
            "machine_candidate" if candidate.status == "candidate" else candidate.status
        )
        learning_status = "waiting_for_time" if learning and learning.active_pointer_status == "rule_only" else (
            "ready" if learning and learning.active_pointer_status == "active" else "unknown"
        )
        return (
            WorkbenchJourneyStep(
                "market",
                "市場總覽",
                "degraded" if decision_snapshot.overall_quality.value == "degraded" else "observed",
                f"{decision_date} 市場快照可讀；品質 {_quality_label(decision_snapshot.overall_quality)}。",
                "DecisionDeskSnapshot.market_regime / market_breadth",
                "開啟市場總覽",
            ),
            WorkbenchJourneyStep(
                "industry",
                "產業探索",
                decision_snapshot.sector_rotation.quality.value,
                _industry_rotation_summary(decision_snapshot.sector_rotation),
                "DecisionDeskSnapshot.sector_rotation",
                "開啟產業探索",
            ),
            WorkbenchJourneyStep(
                "stock_research",
                "個股研究",
                candidate_status,
                f"{len(candidate.symbols)} 檔研究候選；候選不是 Advice、不是 current model，也不是交易指令。",
                "scheduled recommendation snapshot run JSON",
                "開啟候選研究報告" if candidate.symbols else "等待候選來源",
                candidate.symbols,
            ),
            WorkbenchJourneyStep(
                "watchlist",
                "觀察清單",
                decision_snapshot.watchlist_triggers.quality.value,
                f"既有觸發 {decision_snapshot.watchlist_triggers.trigger_count if decision_snapshot.watchlist_triggers.trigger_count is not None else '未知'} 檔；不因每日候選自動新增。",
                "DecisionDeskSnapshot.watchlist_triggers",
                "開啟觀察清單",
                decision_snapshot.watchlist_triggers.triggered_codes,
            ),
            WorkbenchJourneyStep(
                "portfolio",
                "持倉覆盤",
                decision_snapshot.portfolio_alerts.quality.value,
                f"保存快照於 {decision_snapshot.as_of_date.isoformat()} 記錄警示 "
                f"{decision_snapshot.portfolio_alerts.alert_count if decision_snapshot.portfolio_alerts.alert_count is not None else '未知'} 檔；"
                "這不是目前持倉狀態，請以持倉帳本重新核對。",
                f"DecisionDeskSnapshot.portfolio_alerts（資料日 {decision_snapshot.as_of_date.isoformat()}）",
                "開啟持倉管理",
                decision_snapshot.portfolio_alerts.alert_codes,
            ),
            WorkbenchJourneyStep(
                "evidence",
                "Forward evidence",
                evidence.status,
                _evidence_summary(evidence),
                "EvidenceEventRepository + scheduled forward_outcomes receipt",
                evidence.next_action,
            ),
            WorkbenchJourneyStep(
                "learning",
                "Learning receipt",
                learning_status,
                _learning_summary(learning),
                "recommendation_learning/latest_status.json",
                "等待 natural matured evidence" if learning_status == "waiting_for_time" else "查看 learning 詳情",
            ),
        )

    @staticmethod
    def _check_candidate_event_identity(
        candidate: _CandidateRead,
        evidence: _EvidenceRead,
        diagnostics: list[str],
        warnings: list[str],
    ) -> None:
        if not candidate.result_id or not evidence.event_ids:
            return
        matching = False
        for trace in evidence.source_trace:
            if ".source_snapshot_id=" in trace or ".source_id=" in trace:
                if trace.endswith(f"={candidate.result_id}"):
                    matching = True
                    break
        if not matching:
            diagnostics.append("daily_candidate_event_identity_mismatch")
            warnings.append("候選 result_id 與每日 recommendation event identity 未對上")

    @staticmethod
    def _check_wrapper_receipt_counts(
        scheduled_status: ScheduledEvidenceStatus,
        evidence: _EvidenceRead,
        diagnostics: list[str],
        warnings: list[str],
    ) -> None:
        receipt_events = scheduled_status.forward_outcome_events_scanned
        if receipt_events is not None and receipt_events != evidence.event_count:
            diagnostics.append(
                f"scheduled_forward_event_count_mismatch:{evidence.event_count}!={receipt_events}"
            )
            warnings.append("排程 forward receipt 與唯讀事件分母不一致")


def _legacy_payload_candidate_rows(
    payload: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], ...], str | None]:
    """從 query 已驗證的 opaque legacy mapping 做唯讀呈現欄位投影。"""

    raw_rows = payload.get("recommendations")
    if not isinstance(raw_rows, (list, tuple)):
        return (), "recommendation_run_legacy_recommendations_unsupported"
    rows: list[Mapping[str, Any]] = []
    unsupported = False
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            unsupported = True
            break
        row = dict(raw_row)
        if "recommendation_rank" not in row and "rank" in row:
            row["recommendation_rank"] = row["rank"]
        if "recommendation_reason" not in row:
            row["recommendation_reason"] = row.get(
                "recommendation_reasons",
                row.get("推薦理由"),
            )
        if "總分" not in row and "score" not in row and "total_score" in row:
            row["總分"] = row["total_score"]
        rows.append(row)
    if unsupported:
        return (), "recommendation_run_legacy_candidate_rows_unsupported"
    return tuple(rows), None


def _legacy_read_view_matches_projection(
    read_model: RecommendationExecutionReadModel,
    projection: Any,
) -> bool:
    return (
        read_model.legacy_result is not None
        and projection.source == "registered_legacy_run"
        and read_model.result_id == projection.result_id
        and read_model.artifact_location == projection.data_path
        and read_model.raw_artifact_sha256 == projection.raw_artifact_sha256
        and read_model.integrity_basis == projection.integrity_basis
    )


def _legacy_identity_mismatch(
    status_payload: Mapping[str, Any],
    legacy_payload: Mapping[str, Any],
) -> str | None:
    for field in ("source_id", "source_snapshot_id", "source_snapshot_hash"):
        wrapper_value = _text(status_payload.get(field))
        saved_value = _text(legacy_payload.get(field))
        if wrapper_value and saved_value and wrapper_value != saved_value:
            return field
    return None


def _canonical_candidate_rows(
    read_model: RecommendationExecutionReadModel,
) -> tuple[tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
    execution = read_model.execution
    if execution is None or execution.decision is None:
        return (), {}
    rows: list[Mapping[str, Any]] = []
    for item in execution.decision.items:
        reason = item.reason_text
        if reason is None and item.reasons:
            reason = "; ".join(item.reasons)
        rows.append(
            {
                "stock_code": item.stock_code,
                "stock_name": item.stock_name,
                "industry": item.industry,
                "recommendation_reason": reason,
                "recommendation_rank": item.rank,
                "總分": item.rule_score,
                "ranking_method": item.ranking_method,
            }
        )

    context = execution.context
    result_config = execution_result_config(execution)
    run_context: dict[str, Any] = {}
    if context.as_of_date is not None:
        run_context["as_of_date"] = context.as_of_date.isoformat()
    for name in (
        "data_as_of_date",
        "strategy_version_id",
        "strategy_config_id",
        "universe_policy_id",
        "universe_policy_hash",
        "universe_snapshot_id",
        "universe_snapshot_hash",
        "cost_model_id",
        "benchmark_id",
        "horizon_days",
        "cost_scenario_id",
        "learning_candidate_id",
        "candidate_id",
        "return_basis",
    ):
        value = result_config.get(name)
        if value is not None:
            run_context[name] = value
    strategy = context.strategy_identity
    if strategy is not None:
        for name in ("strategy_version_id", "strategy_config_id"):
            value = getattr(strategy, name)
            if value is not None:
                run_context[name] = value
    universe = context.universe_identity
    if universe is not None:
        policy = universe.policy
        if policy is not None:
            for name in ("universe_policy_id", "universe_policy_hash"):
                value = getattr(policy, name)
                if value is not None:
                    run_context[name] = value
        snapshot = universe.snapshot
        if snapshot is not None:
            for name in ("universe_snapshot_id", "universe_snapshot_hash"):
                value = getattr(snapshot, name)
                if value is not None:
                    run_context[name] = value
    evidence = context.evidence_identity
    if evidence is not None:
        if evidence.return_basis is not None:
            run_context["return_basis"] = evidence.return_basis
        if evidence.cost_model_id is not None:
            run_context["cost_model_id"] = evidence.cost_model_id
        if evidence.benchmark_id is not None:
            run_context["benchmark_id"] = evidence.benchmark_id
        if evidence.horizon_days is not None:
            run_context["horizon_days"] = evidence.horizon_days
    return tuple(rows), run_context


def _canonical_cohort(read_model: RecommendationExecutionReadModel) -> dict[str, Any]:
    execution = read_model.execution
    if execution is None:
        return {}
    cohort = execution.context.snapshot_cohort
    if cohort is not None:
        result: dict[str, Any] = {
            "cohort_hash": cohort.cohort_hash,
            "requested_count": cohort.requested_count,
            "eligible_count": cohort.eligible_count,
            "degraded_count": cohort.degraded_count,
            "missing_count": cohort.missing_count,
            "coverage_status": cohort.coverage_status.value,
        }
    else:
        result = {}
    result_config = execution_result_config(execution)
    saved_cohort = result_config.get("snapshot_cohort")
    if not result and isinstance(saved_cohort, Mapping):
        result.update(saved_cohort)
    universe = execution.context.universe_identity
    if universe is not None:
        if universe.policy is not None:
            result.setdefault("universe_policy_id", universe.policy.universe_policy_id)
            result.setdefault("universe_policy_hash", universe.policy.universe_policy_hash)
        if universe.snapshot is not None:
            result.setdefault("universe_snapshot_id", universe.snapshot.universe_snapshot_id)
            result.setdefault("universe_snapshot_hash", universe.snapshot.universe_snapshot_hash)
    for name in (
        "universe_policy_id",
        "universe_policy_hash",
        "universe_snapshot_id",
        "universe_snapshot_hash",
    ):
        if name in result_config:
            result.setdefault(name, result_config[name])
    return result


def _canonical_identity_mismatch(
    status_payload: Mapping[str, Any],
    status_cohort: Mapping[str, Any],
    execution_context: Mapping[str, Any],
) -> str | None:
    status_evidence_identity = _mapping(status_payload.get("evidence_identity"))
    comparisons = (
        ("strategy_version_id", status_evidence_identity, execution_context),
        ("strategy_config_id", status_evidence_identity, execution_context),
        ("universe_policy_id", status_evidence_identity, execution_context),
        ("universe_policy_hash", status_evidence_identity, execution_context),
        ("universe_snapshot_id", status_evidence_identity, execution_context),
        ("universe_snapshot_hash", status_evidence_identity, execution_context),
        ("cost_model_id", status_evidence_identity, execution_context),
        ("benchmark_id", status_evidence_identity, execution_context),
        ("return_basis", status_evidence_identity, execution_context),
        ("horizon_days", status_evidence_identity, execution_context),
        ("universe_policy_id", status_cohort, execution_context),
        ("universe_policy_hash", status_cohort, execution_context),
        ("universe_snapshot_id", status_cohort, execution_context),
        ("universe_snapshot_hash", status_cohort, execution_context),
    )
    for name, left, right in comparisons:
        saved_value = _text(left.get(name))
        execution_value = _text(right.get(name))
        if saved_value and execution_value and saved_value != execution_value:
            return name
    return None


def _fallback_lane(
    projection: RecommendationLearningEvidenceProjection | None,
) -> Any | None:
    if projection is None:
        return None
    scoped_lane_id = str(getattr(projection, "horizon_scope_lane_id", "") or "")
    if scoped_lane_id == projection.candidate_lane.lane_id:
        return projection.candidate_lane
    if scoped_lane_id == projection.active_lane.lane_id:
        return projection.active_lane
    verified = projection.verified_lane
    if verified is not None:
        return verified
    for lane in (projection.candidate_lane, projection.active_lane):
        if getattr(lane, "horizons", ()):
            return lane
    for lane in (projection.candidate_lane, projection.active_lane):
        if str(getattr(lane, "status", "")) not in {"not_applicable", "unknown", "missing"}:
            return lane
    return projection.candidate_lane


def _fallback_status(
    *,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    projection: RecommendationLearningEvidenceProjection | None,
) -> str:
    projection_status = str(getattr(projection, "status", "")) if projection is not None else ""
    lane = _fallback_lane(projection)
    lane_status = str(getattr(lane, "status", "")) if lane is not None else ""
    reason_values = (
        projection_status,
        str(getattr(projection, "data_recorded_reason", "")) if projection is not None else "",
        str(getattr(projection, "decision_reason", "")) if projection is not None else "",
        str(getattr(lane, "reason", "")) if lane is not None else "",
        *(str(item) for item in (getattr(projection, "diagnostics", ()) if projection is not None else ())),
        *(str(item) for item in (getattr(lane, "diagnostics", ()) if lane is not None else ())),
    )
    reason_text = " ".join(reason_values).lower()
    if (
        evidence.status == "read_failure"
        or candidate.status == "read_failure"
        or projection_status == "read_failure"
    ):
        return "read_failure"
    if (
        candidate.status in {"future_blocked", "stale"}
        or projection_status in {"future_blocked", "stale"}
    ):
        return "blocked_scope"
    if (
        projection_status == "blocked_provenance"
        or lane_status == "blocked_provenance"
    ) and _fallback_is_identity_or_cost_conflict(reason_text):
        return "blocked_identity_or_cost"
    if projection_status == "blocked_provenance" or lane_status == "blocked_provenance":
        return "blocked_provenance"
    if (
        evidence.event_count == 0
        or evidence.outcome_missing > 0
        or candidate.status in {"missing", "candidate_degraded", "degraded"}
    ):
        return "missing_data"
    if projection is not None and projection.verified_lane is not None:
        return "not_needed"
    if (
        projection is not None
        and (
            projection.data_recorded_status == "recorded"
            or (
                projection.data_recorded_status not in {"not_recorded", "unknown"}
                and (projection_status == "pending" or lane_status == "pending")
            )
        )
    ):
        return "pending_natural_evidence"
    if (
        projection is not None
        and projection.data_recorded_status in {"not_recorded", "unknown"}
        and projection_status not in {"missing", "unknown"}
    ):
        return "pending_capture"
    if evidence.status == "waiting_for_time" or evidence.outcome_pending > 0:
        return "pending_natural_evidence"
    if projection is None:
        return "missing_source"
    if projection_status in {"missing", "unknown"}:
        return "missing_source"
    return "unknown"


def _fallback_is_identity_or_cost_conflict(reason_text: str) -> bool:
    return any(
        marker in reason_text
        for marker in (
            "mismatch",
            "不一致",
            "cross-capture",
            "cost_scope",
            "cost scenario",
            "cost_scenario",
            "hash_mismatch",
            "capture_content_hash",
            "source conflict",
            "身份衝突",
        )
    )


def _fallback_missing_reason(
    *,
    status: str,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    projection: RecommendationLearningEvidenceProjection | None,
    candidate_reason: str,
    evidence_reason: str,
    lane: Any | None,
) -> str:
    if status == "not_needed":
        return "同一 scope 已有 typed natural evidence verifier 結果；本輪不需補研究 fallback。"
    parts: list[str] = []
    if status == "missing_data":
        if candidate_reason:
            parts.append(candidate_reason)
        if evidence_reason:
            parts.append(evidence_reason)
        if not parts:
            parts.append("candidate／EvidenceEvent／outcome 欄位不足，無法形成完整 scope。")
    elif status == "read_failure":
        parts.append("既有唯讀來源讀取失敗；不能把讀取失敗解讀成沒有資料。")
    elif status == "blocked_scope":
        parts.append("既有來源日期超出或落後本次決策 scope；不沿用成為 current evidence。")
    elif status == "blocked_identity_or_cost":
        parts.append("同一決策日的 candidate／capture／source identity 或 cost lane 不一致。")
    elif status == "blocked_provenance":
        parts.append("typed natural evidence provenance 未通過；receipt 宣稱不能取代 verifier。")
    elif status == "pending_capture":
        parts.append("本日 scheduled live prediction capture 尚未記錄或尚未能核對。")
    elif status == "pending_natural_evidence":
        parts.append("capture／forward evidence 尚未自然成熟，或尚缺 typed natural receipt。")
    elif status == "missing_source":
        parts.append("learning projection 或其既有來源缺失；目前無法判定 capture／natural maturity。")
    else:
        parts.append("目前 evidence 狀態未知；沒有足夠證據形成正向結論。")
    if projection is not None:
        for value in (
            projection.data_recorded_reason,
            getattr(lane, "reason", "") if lane is not None else "",
        ):
            text = str(value or "").strip()
            if text and text not in parts:
                parts.append(text)
        if status in {"pending_natural_evidence", "pending_capture"} and projection.next_gap:
            parts.append(str(projection.next_gap))
    return "；".join(dict.fromkeys(parts))


def _fallback_research_question(
    *,
    status: str,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    projection: RecommendationLearningEvidenceProjection | None,
) -> str:
    if status == "not_needed":
        return "本輪是否仍需補件？目前沒有待補的 natural evidence 欄位。"
    if status == "missing_data":
        return "本日 candidate、cohort identity 與 outcome 是否都能沿同一決策日核對？"
    if status == "read_failure":
        return "既有來源是否可在不寫入、不重算的前提下重新讀取？"
    if status == "blocked_scope":
        return "來源日期是否與本次決策日一致，且沒有把未來資料帶回當日？"
    if status == "blocked_identity_or_cost":
        return "candidate、capture、source 與 cost scenario 是否屬同一決策日同一 scope？"
    if status == "blocked_provenance":
        return "既有 receipt 是否能由 typed verifier 核對完整 lineage 與 authority？"
    if status == "pending_capture":
        return "同一 candidate／決策日是否有可驗證的 scheduled live capture？"
    if status == "pending_natural_evidence":
        return "同一 capture 的 natural outcome 是否已達 horizon 並通過 typed verifier？"
    if projection is None:
        return "既有 learning projection 是否可讀，且能確認相同決策日與成本 scope？"
    return "目前還缺哪個可核對的 evidence 欄位，才能停止研究中狀態？"


def _fallback_next_step(
    *,
    status: str,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    projection: RecommendationLearningEvidenceProjection | None,
    lane: Any | None,
) -> str:
    if status == "not_needed":
        return "依既有 Evidence／decision review 閱讀；UI 不改寫正式決策，也不要求新增批准。"
    if status == "missing_data":
        return "補／核對同一決策日的 candidate、EvidenceEvent identity 與 outcome 缺件，再重新整理 Workbench。"
    if status == "read_failure":
        return "檢查既有 DB／receipt／snapshot 路徑後重新整理唯讀來源；不要由 UI 執行 runner 或重算。"
    if status == "blocked_scope":
        return "先確認決策日與資料日 scope；移除未來／過期來源後重新讀取，不回填日期。"
    if status == "blocked_identity_or_cost":
        return "逐一核對 decision date、source snapshot、candidate／capture identity 與 cost lane；修復後重讀 typed projection。"
    if status == "blocked_provenance":
        return "保留 blocked 狀態，修復既有 lineage／receipt verifier 缺口後再重新整理。"
    if status == "pending_capture":
        return "補上同一 candidate／決策日的 scheduled live capture，核對 source identity 與 cost lane 後再整理。"
    if status == "pending_natural_evidence":
        return "維持同一 capture scope，等待自然 outcome 成熟，再回看 typed receipt；期間不補值。"
    if projection is None:
        return "重新整理既有 learning projection 與 source trace，確認缺件後再決定研究問題。"
    return "先查看既有 projection 的 source trace 與缺口，再重新整理；未證明前維持研究中。"


def _fallback_limitations(
    *,
    projection: RecommendationLearningEvidenceProjection | None,
    historical_research_allowed: bool,
) -> tuple[str, ...]:
    limitations = [
        "這是唯讀 research fallback；不提供有效機率、score、權重或買賣結論。",
        "只有同 scope 且由 typed verifier 通過的 natural evidence 才能支持 reliability；不以 receipt 宣稱或 80% 補值。",
        "來源 owner 未由既有 DTO／receipt 提供；unknown 不代表已指派 owner。",
    ]
    if historical_research_allowed and projection is not None:
        note = str(projection.historical_evaluation_note or "").strip()
        limitations.append(
            note
            or "已有 historical replay／evaluation；可研究比較，但不能與 natural evidence 混算。"
        )
    else:
        limitations.append("若只剩 historical replay／evaluation，只能作研究比較，不能當 natural evidence。")
    return tuple(dict.fromkeys(limitations))


def _fallback_natural_status(
    projection: RecommendationLearningEvidenceProjection | None,
    evidence: _EvidenceRead,
) -> str:
    if projection is not None and projection.verified_lane is not None:
        return "verified"
    lane = _fallback_lane(projection)
    if lane is not None and str(getattr(lane, "status", "")).strip():
        return str(getattr(lane, "status"))
    if evidence.status == "waiting_for_time" or evidence.outcome_pending > 0:
        return "pending"
    return "unknown"


def _fallback_revisit(
    *,
    status: str,
    decision_date: str,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    projection: RecommendationLearningEvidenceProjection | None,
    calendar: Any | None,
) -> tuple[str | None, str, str, str]:
    if status != "pending_natural_evidence":
        return None, "unknown", "", "只有自然成熟等待狀態才有可估的 revisit horizon。"
    horizon_days = _fallback_horizon_days(projection)
    if horizon_days is None:
        return (
            None,
            "unknown",
            "",
            "缺少可證明的正整數 horizon；不以日曆天數假造 revisit date。",
        )
    anchors = _matching_pending_horizon_anchors(candidate, evidence, horizon_days)
    anchor_dates = tuple(dict.fromkeys(anchor.decision_date for anchor in anchors))
    if len(anchor_dates) != 1:
        return (
            None,
            "unknown",
            "",
            "沒有唯一同 scope pending event 的原決策日；不以 Workbench 查看日倒填 revisit date。",
        )
    if not _pending_anchor_proves_learning_scope(anchors[0], candidate, projection):
        return (
            None,
            "unknown",
            "",
            "forward cohort 尚未證明與 learning candidate、cost scenario、return basis 完整對應；不估算 revisit date。",
        )
    try:
        anchor = date.fromisoformat(anchors[0].decision_date)
    except (TypeError, ValueError):
        return None, "unknown", "", "同 scope pending event 的原決策日無法解析；不倒填 revisit date。"
    if decision_date != "unknown" and anchor > date.fromisoformat(decision_date[:10]):
        return None, "unknown", "", "pending event 原決策日晚於 Workbench 決策日；不使用未來 anchor。"
    if calendar is None:
        return None, "unknown", "", "官方交易日曆不可用；不以週一至週五或日曆天數推定。"
    current = anchor
    counted = 0
    max_scan_days = max(366, horizon_days * 10 + 31)
    for _ in range(max_scan_days):
        current += timedelta(days=1)
        try:
            resolved = calendar.is_official_trading_day(
                current,
                allow_online_probe=False,
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            return None, "unknown", "", f"官方交易日曆讀取失敗（{type(exc).__name__}）；不假造日期。"
        if not isinstance(resolved, tuple) or len(resolved) < 2:
            return None, "unknown", "", "官方交易日曆未回傳可核對結果；不假造日期。"
        is_trading_day, reason = resolved[0], str(resolved[1])
        if is_trading_day is None:
            return (
                None,
                "unknown",
                "",
                f"官方交易日曆未知（{current.isoformat()}：{reason}）；不假造 revisit date。",
            )
        if is_trading_day:
            counted += 1
            if counted >= horizon_days:
                return (
                    current.isoformat(),
                    "estimated_official_trading_day",
                    "OfficialTradingCalendar + horizon_trading_days",
                    f"以決策日後 {horizon_days} 個已解析官方交易日估算；下一輪仍須重新核對實際 maturity。",
                )
    return None, "unknown", "", "官方交易日曆掃描範圍不足；不假造 revisit date。"


def _fallback_horizon_days(
    projection: RecommendationLearningEvidenceProjection | None,
) -> int | None:
    if projection is None:
        return None
    lane = _fallback_lane(projection)
    if lane is None:
        return None
    for horizon in getattr(lane, "horizons", ()):
        raw = getattr(horizon, "horizon_days", None)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            value = raw
        elif isinstance(raw, str) and raw.strip().isdigit():
            value = int(raw.strip())
        else:
            continue
        if value > 0:
            return value
    return None


def _matching_pending_horizon_anchors(
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    horizon_days: int,
) -> tuple[_PendingHorizonAnchor, ...]:
    return tuple(
        anchor
        for anchor in evidence.pending_horizon_anchors
        if anchor.horizon_days == horizon_days
        and _pending_anchor_matches_candidate(anchor, candidate)
    )


def _pending_anchor_from_event(
    event: EvidenceEvent,
    outcome: EvidenceOutcome | None,
    *,
    horizon_days: int = 0,
    decision_date: str | None = None,
) -> _PendingHorizonAnchor:
    identity = dict(_event_identity_pairs(event))
    return_basis = (
        _text(getattr(outcome, "return_basis", None)) or None
        if outcome is not None
        else None
    )
    if return_basis:
        identity["return_basis"] = return_basis
    return _PendingHorizonAnchor(
        horizon_days=horizon_days,
        decision_date=decision_date or _date_key(getattr(event, "decision_date", None)) or "unknown",
        symbol=_text(getattr(event, "symbol", None)) or None,
        source_id=_text(getattr(event, "source_id", None)) or None,
        source_snapshot_id=_text(getattr(event, "source_snapshot_id", None)) or None,
        identity=tuple(sorted(identity.items())),
        window_type=(
            _text(getattr(outcome, "window_type", None)) or None
            if outcome is not None
            else None
        ),
        return_basis=return_basis,
    )


def _event_identity_pairs(event: EvidenceEvent) -> tuple[tuple[str, str], ...]:
    metadata_raw = getattr(event, "metadata", {})
    metadata = metadata_raw if isinstance(metadata_raw, Mapping) else {}
    specs: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
        ("result_id", (), ("result_id", "source_result_id", "recommendation_result_id", "run_result_id")),
        ("strategy_version_id", ("strategy_version_id",), ("strategy_version_id", "strategy_version")),
        ("strategy_config_id", (), ("strategy_config_id",)),
        ("strategy_config_hash", (), ("strategy_config_hash",)),
        ("cost_model_id", ("cost_model_id",), ("cost_model_id",)),
        ("cost_scenario_id", (), ("cost_scenario_id",)),
        ("benchmark_id", ("benchmark_id",), ("benchmark_id",)),
        ("industry_benchmark_id", ("industry_benchmark_id",), ("industry_benchmark_id",)),
        ("universe_policy_id", (), ("universe_policy_id",)),
        ("universe_policy_hash", (), ("universe_policy_hash",)),
        ("universe_snapshot_id", (), ("universe_snapshot_id",)),
        ("universe_snapshot_hash", (), ("universe_snapshot_hash",)),
        ("cohort_hash", (), ("cohort_hash",)),
        ("horizon_days", (), ("horizon_days", "expected_horizon_days")),
        ("learning_candidate_id", (), ("learning_candidate_id", "candidate_id")),
        ("run_context.as_of_date", ("as_of_date",), ("as_of_date",)),
        ("run_context.data_as_of_date", (), ("data_as_of_date", "data_as_of")),
    )
    values: dict[str, str] = {}
    for key, event_attributes, metadata_keys in specs:
        value = ""
        for attribute in event_attributes:
            value = _text(getattr(event, attribute, None))
            if value:
                break
        if not value:
            for metadata_key in metadata_keys:
                value = _text(metadata.get(metadata_key))
                if value:
                    break
        if not value and key == "run_context.data_as_of_date":
            value = _text(getattr(event, "as_of_date", None))
        if value:
            values[key] = value
    return tuple(sorted(values.items()))


def _candidate_identity_map(candidate: _CandidateRead) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in candidate.identity:
        key, separator, value = _text(item).partition("=")
        if separator and key.strip() and value.strip():
            values[key.strip()] = value.strip()
    return values


def _pending_anchor_matches_candidate(
    anchor: _PendingHorizonAnchor,
    candidate: _CandidateRead,
) -> bool:
    candidate_source_id = _text(candidate.source_id)
    candidate_snapshot_id = _text(candidate.source_snapshot_id)
    if not candidate_source_id or not candidate_snapshot_id:
        return False
    if anchor.source_id != candidate_source_id or anchor.source_snapshot_id != candidate_snapshot_id:
        return False
    if not anchor.symbol or not candidate.symbols or anchor.symbol not in candidate.symbols:
        return False

    actual = dict(anchor.identity)
    expected = _candidate_identity_map(candidate)
    candidate_result_id = _text(candidate.result_id)
    actual_result_id = actual.get("result_id", "")
    if candidate_result_id:
        if actual_result_id:
            if actual_result_id != candidate_result_id:
                return False
        elif candidate_result_id != candidate_source_id:
            # Existing recommendation importer uses source_id as the result id;
            # a distinct result id needs an explicit event metadata binding.
            return False
    for key, expected_value in expected.items():
        actual_key = "result_id" if key == "run.result_id" else key
        actual_value = actual.get(actual_key)
        if actual_value is None or actual_value != expected_value:
            return False
    return True


def _single_identity_value(values: Mapping[str, str], keys: tuple[str, ...]) -> str | None:
    present = tuple(dict.fromkeys(values.get(key, "") for key in keys if values.get(key, "")))
    return present[0] if len(present) == 1 else None


def _pending_anchor_proves_learning_scope(
    anchor: _PendingHorizonAnchor,
    candidate: _CandidateRead,
    projection: RecommendationLearningEvidenceProjection | None,
) -> bool:
    if projection is None:
        return False
    expected = _candidate_identity_map(candidate)
    actual = dict(anchor.identity)
    lane = _fallback_lane(projection)
    if lane is None:
        return False
    learning_candidate_id = expected.get("learning_candidate_id") or expected.get("candidate_id")
    lane_candidate_id = _text(getattr(lane, "candidate_id", None))
    if not learning_candidate_id or not lane_candidate_id or learning_candidate_id != lane_candidate_id:
        return False
    candidate_cost = _single_identity_value(expected, ("cost_scenario_id", "cost_model_id"))
    anchor_cost = _single_identity_value(actual, ("cost_scenario_id", "cost_model_id"))
    projection_cost = _text(
        getattr(projection, "horizon_scope_cost_scenario_id", None)
        or getattr(lane, "cost_scenario_id", None)
    )
    if not candidate_cost or not anchor_cost or not projection_cost:
        return False
    if len({candidate_cost, anchor_cost, projection_cost}) != 1:
        return False
    if anchor.window_type != "trading_days" or anchor.return_basis != DEFAULT_RETURN_BASIS:
        return False
    return True


def _matched_source_snapshot_id(
    events: Iterable[EvidenceEvent],
    candidate: _CandidateRead,
) -> str | None:
    matched = {
        str(event.source_snapshot_id).strip()
        for event in events
        if _pending_anchor_matches_candidate(_pending_anchor_from_event(event, None), candidate)
        and str(event.source_snapshot_id or "").strip()
    }
    return next(iter(matched)) if len(matched) == 1 else None


def _pending_horizon_anchors(
    events: Iterable[EvidenceEvent],
    outcomes: Iterable[EvidenceOutcome],
    windows: tuple[int, ...],
    *,
    requested_date: str | None,
) -> tuple[_PendingHorizonAnchor, ...]:
    event_list = tuple(events)
    by_key: dict[tuple[str, int], EvidenceOutcome] = {}
    for outcome in outcomes:
        if outcome.window_days not in windows:
            continue
        key = (str(outcome.event_id), int(outcome.window_days))
        current = by_key.get(key)
        if current is None or _outcome_preference(outcome) < _outcome_preference(current):
            by_key[key] = outcome
    anchors: list[_PendingHorizonAnchor] = []
    for event in event_list:
        event_date = _date_key(event.decision_date)
        if event_date is None:
            continue
        if requested_date and requested_date != "unknown" and event_date > requested_date:
            continue
        for window in windows:
            selected_outcome = by_key.get((str(event.event_id), window))
            if selected_outcome is None:
                continue
            state = _text(
                getattr(
                    selected_outcome.outcome_status,
                    "value",
                    selected_outcome.outcome_status,
                )
            )
            if state in {"pending", "insufficient_future_data"}:
                anchors.append(
                    _pending_anchor_from_event(
                        event,
                        selected_outcome,
                        horizon_days=int(window),
                        decision_date=event_date,
                    )
                )
    return tuple(dict.fromkeys(anchors))


def _candidate_fallback_reason(candidate: _CandidateRead) -> str:
    if candidate.status == "missing":
        return "每日 recommendation candidate source 缺失。"
    if candidate.status == "read_failure":
        return "每日 recommendation candidate source 讀取失敗。"
    if candidate.status in {"candidate_degraded", "degraded"}:
        return candidate.reasons[0] if candidate.reasons else "candidate source 降級，仍有欄位缺件。"
    return ""


def _evidence_fallback_reason(evidence: _EvidenceRead) -> str:
    if evidence.status == "read_failure":
        return "EvidenceEvent／Outcome 唯讀查詢失敗。"
    if evidence.event_count == 0:
        return _evidence_summary(evidence)
    if evidence.outcome_missing > 0:
        return f"Forward outcome 缺件 {evidence.outcome_missing} 筆；不能把缺件當成未獲利。"
    if evidence.outcome_pending > 0:
        return f"Forward outcome 尚待自然成熟 {evidence.outcome_pending} 筆。"
    return ""


def _project_learning_receipt(
    payload: Mapping[str, Any] | None,
    *,
    requested_date: str | None = None,
) -> WorkbenchLearningReceipt | None:
    if not isinstance(payload, Mapping):
        return None
    receipt = _mapping(payload.get("decision_receipt"))
    candidate = _mapping(payload.get("candidate") or payload.get("challenger"))
    pointer = _mapping(payload.get("active_pointer"))
    natural = _mapping(payload.get("active_model_natural_evidence"))
    performance = _mapping(payload.get("active_model_performance"))
    candidate_id = _text(payload.get("candidate_id")) or _text(candidate.get("candidate_id"))
    active_candidate_id = _text(pointer.get("candidate_id"))
    pointer_status = _text(pointer.get("status")) or "unknown"
    if candidate_id and pointer_status == "active" and active_candidate_id == candidate_id:
        candidate_status = "active_model"
    elif candidate_id:
        candidate_status = "challenger_candidate"
    else:
        candidate_status = "none"
    # Preserve an explicit zero.  The top-level / decision receipt count is
    # deliberately separate from the challenger and active-model counts.
    natural_sample_count = _first_int(
        (payload, "natural_matured_sample_count"),
        (receipt, "natural_matured_sample_count"),
    )
    date_count = _first_int(
        (payload, "natural_matured_decision_date_count"),
        (receipt, "natural_matured_decision_date_count"),
    )
    candidate_natural_sample_count = _first_int(
        (candidate, "last_evaluated_matured_sample_count"),
        (candidate, "natural_matured_sample_count"),
    )
    candidate_natural_date_count = _first_int(
        (candidate, "last_evaluated_decision_date_count"),
        (candidate, "natural_matured_decision_date_count"),
    )
    active_natural_sample_count = _first_int((natural, "matured_sample_count"))
    active_natural_date_count = _first_int((natural, "matured_decision_date_count"))
    diagnostics = list(_strings(payload.get("warnings")))
    if not _text(payload.get("cli_schema_version")) and not _text(payload.get("schema_version")):
        diagnostics.append("recommendation_learning_schema_version_missing")
    learning_date = _date_key(payload.get("decision_date") or receipt.get("decision_date"))
    if requested_date and learning_date and learning_date != requested_date:
        if learning_date > requested_date:
            diagnostics.append(
                f"recommendation_learning_future_date:{learning_date}:requested={requested_date}"
            )
        else:
            diagnostics.append(
                f"recommendation_learning_stale_date:{learning_date}:requested={requested_date}"
            )
    trace = [
        f"recommendation_learning.schema={_text(payload.get('cli_schema_version') or payload.get('schema_version')) or 'unknown'}",
        f"recommendation_learning.decision_date={learning_date or 'unknown'}",
        f"recommendation_learning.active_pointer.status={pointer_status}",
    ]
    decision_id = _text(receipt.get("decision_id")) or _text(payload.get("decision_id"))
    decision_hash = _text(
        receipt.get("decision_receipt_hash")
        or receipt.get("receipt_hash")
        or payload.get("decision_receipt_hash")
    )
    if decision_id:
        trace.append(f"recommendation_learning.decision_receipt.decision_id={decision_id}")
    if decision_hash:
        trace.append(f"recommendation_learning.decision_receipt.hash={decision_hash}")
    return WorkbenchLearningReceipt(
        schema_version=_text(payload.get("cli_schema_version") or payload.get("schema_version")) or "unknown",
        status=_text(payload.get("status")) or "unknown",
        decision_date=_date_key(payload.get("decision_date") or receipt.get("decision_date")),
        checked_at=(
            _text(payload.get("cli_result_updated_at"))
            or _text(payload.get("checked_at"))
            or _text(payload.get("completed_at"))
        ),
        decision=_text(payload.get("decision") or receipt.get("decision")) or "unknown",
        decision_reason=_text(payload.get("decision_reason") or receipt.get("decision_reason")) or "",
        candidate_id=candidate_id or None,
        candidate_status=candidate_status,
        active_pointer_status=pointer_status,
        active_candidate_id=active_candidate_id or None,
        active_effective_date=_date_key(pointer.get("effective_date")),
        active_model_performance_status=_text(performance.get("status")) or "unknown",
        active_model_performance_reason=_text(performance.get("reason")) or "",
        active_natural_evidence_status=_text(natural.get("status")) or "unknown",
        active_natural_evidence_reason=_text(natural.get("reason")) or "",
        natural_matured_sample_count=natural_sample_count,
        natural_matured_decision_date_count=date_count,
        candidate_natural_matured_sample_count=candidate_natural_sample_count,
        candidate_natural_matured_decision_date_count=candidate_natural_date_count,
        active_natural_matured_sample_count=active_natural_sample_count,
        active_natural_matured_decision_date_count=active_natural_date_count,
        shadow_only=_bool_or_none(payload.get("shadow_only")),
        formal_order_allowed=_bool_or_none(payload.get("formal_order_allowed")),
        decision_receipt_id=decision_id or None,
        decision_receipt_hash=decision_hash or None,
        diagnostics=tuple(diagnostics),
        source_trace=tuple(trace),
    )


def _overall_status(
    *,
    decision_snapshot: DecisionDeskSnapshot | None,
    scheduled_status: ScheduledEvidenceStatus,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    diagnostics: Iterable[str],
) -> str:
    diagnostic_values = tuple(diagnostics)
    if any("read_failure" in item or "invalid" in item for item in diagnostic_values):
        return "read_failure"
    if any(
        "recommendation_learning_stale_date" in item
        or "recommendation_learning_future_date" in item
        for item in diagnostic_values
    ):
        return "stale"
    if candidate.status in {"future_blocked", "stale"}:
        return candidate.status
    if decision_snapshot is None or evidence.status == "missing":
        return "missing" if decision_snapshot is None and candidate.status == "missing" else "degraded"
    if scheduled_status.is_stale or scheduled_status.load_state == "stale":
        return "stale"
    if evidence.status == "waiting_for_time":
        return "waiting_for_time"
    if evidence.status in {"read_failure", "degraded"} or candidate.status in {"candidate_degraded", "degraded"}:
        return "degraded"
    if decision_snapshot.overall_quality.value in {"degraded", "missing"}:
        return "degraded"
    return "ready"


def _headline(
    *,
    decision_date: str,
    decision_snapshot: DecisionDeskSnapshot | None,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    learning: WorkbenchLearningReceipt | None,
    status: str,
) -> str:
    if decision_snapshot is None:
        return "今日市場快照缺失，暫不能形成投資結論；請先檢查來源後再進行人工覆盤。"
    if status in {"stale", "future_blocked", "read_failure", "missing"}:
        return "今日來源未達可直接採用狀態，暫不形成投資結論；請先重新整理並檢查資料日期。"
    regime = decision_snapshot.market_regime.regime_label or "市場狀態未知"
    candidate_text = (
        f"{len(candidate.symbols)} 檔（{', '.join(candidate.symbols[:5])}）"
        if candidate.symbols
        else "目前沒有可安全呈現的研究候選"
    )
    portfolio_alert_count = decision_snapshot.portfolio_alerts.alert_count
    portfolio_date = decision_snapshot.as_of_date.isoformat()
    if portfolio_alert_count is None:
        portfolio_text = f"{portfolio_date} 快照中的持倉警示數未知，需查原始快照"
    else:
        portfolio_text = (
            f"{portfolio_date} 快照記錄 {portfolio_alert_count} 檔持倉警示，"
            "需以目前帳本核對"
        )
    if evidence.outcome_pending > 0:
        evidence_surface = "證據結果尚待後續交易日成熟"
    elif evidence.outcome_ready > 0 and evidence.outcome_missing == 0:
        evidence_surface = "證據結果已具備可讀觀測"
    elif evidence.outcome_missing > 0:
        evidence_surface = "證據仍有缺件，需先檢查來源"
    else:
        evidence_surface = "證據結果尚未形成"
    if learning is None:
        learning_surface = "模型學習來源缺失"
    elif (
        learning.active_pointer_status == "active"
        and learning.active_natural_matured_sample_count is not None
        and learning.active_natural_matured_sample_count > 0
    ):
        learning_surface = "模型已有自然成熟樣本，可進一步複核"
    else:
        learning_surface = "模型尚待自然成熟樣本，今日候選僅供研究"
    return (
        f"盤勢：{regime}；今日研究候選：{candidate_text}；{portfolio_text}"
        "（來源 DecisionDeskSnapshot.portfolio_alerts；不代表目前持倉狀態）。"
        f"{evidence_surface}；{learning_surface}。"
    )


def _industry_rotation_summary(rotation: Any) -> str:
    """以來源可證明的語意呈現產業輪動，避免把代理指數冒充產業本身。"""

    quality = _quality_label(getattr(rotation, "quality", None))
    strength = getattr(rotation, "industry_strength", None)
    if strength is not None:
        rows = tuple(getattr(strength, "rows", ()) or ())
        if not rows:
            missing_categories = "、".join(
                getattr(strength, "unmapped_industry_categories", ())[:3]
            ) or "無"
            return (
                f"產業：可比產業 read model 缺少可排名列｜品質 {quality}｜"
                f"映射 {getattr(strength, 'mapping_version', '未知')}｜"
                f"未映射類別 {missing_categories}｜current research only"
            )
        leading = str(getattr(rotation, "leading_sector", None) or "未定義")
        trailing = str(getattr(rotation, "trailing_sector", None) or "未定義")
        by_name = {item.industry_name: item for item in rows}
        leading_row = by_name.get(leading)
        return (
            f"產業：可比純產業指數（相對 TAIEX）｜領先 {leading}、落後 {trailing}｜"
            f"5日／20日超額BP "
            f"{getattr(leading_row, 'excess_5d_bp', None) if leading_row else '未知'}／"
            f"{getattr(leading_row, 'excess_20d_bp', None) if leading_row else '未知'}｜"
            f"覆蓋 {getattr(leading_row, 'coverage_20d_bp', None) if leading_row else '未知'} bp｜"
            f"資料日 {getattr(strength, 'as_of_date', None) or '未知'}｜"
            f"來源 {getattr(strength, 'source_id', '未知')}｜"
            f"映射 {getattr(strength, 'mapping_version', '未知')}｜"
            f"current research only；品質 {quality}"
        )
    leading = str(getattr(rotation, "leading_sector", None) or "").strip()
    trailing = str(getattr(rotation, "trailing_sector", None) or "").strip()
    labels = "、".join(item for item in (leading, trailing) if item)
    proxy_markers = ("兩倍", "二倍", "正2", "反1", "反向", "槓桿", "倍數")
    if labels and any(marker in labels for marker in proxy_markers):
        return "產業：市場指數代理（含槓桿／反向名稱）；缺產業分類，暫不判定強弱"
    if labels or (
        isinstance(getattr(rotation, "meta", None), Mapping)
        and getattr(rotation, "meta", {}).get("source") == "sqlite_industry_indices"
    ):
        return "產業：產業指數代理；缺分類映射，暫不判定強弱"
    return f"產業：缺可驗證的產業分類，不能判定領先／落後｜品質 {quality}"


def _quality_label(value: Any) -> str:
    raw = str(getattr(value, "value", value) or "unknown").strip().lower()
    return {
        "observed": "可讀",
        "ready": "已就緒",
        "degraded": "降級",
        "missing": "缺漏",
        "estimated": "估計",
        "unknown": "未知",
    }.get(raw, raw)


def _next_action(
    *,
    status: str,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    scheduled_status: ScheduledEvidenceStatus,
) -> str:
    if status in {"missing", "read_failure"}:
        return "先重新整理唯讀來源，確認資料日期、scope receipt 與正式 EvidenceEvent table。"
    if status == "stale":
        return "先重新讀取今日來源；目前只保留 stale 參考，不把舊資料當作 current。"
    if candidate.status in {"missing", "degraded"}:
        return "先檢查 recommendation snapshot 與 run JSON；不可用空白候選推導結論。"
    if evidence.status == "waiting_for_time":
        return "等待下一個官方交易日的可見價格觀測；成熟前不回填、不補未來資料。"
    if scheduled_status.pipeline_overall_status in {"invalid_evidence", "blocked"}:
        return "先查看 Evidence scope 與 identity gate；pipeline 未達可驗證狀態。"
    return "開啟候選的既有個股研究報告，並依市場、產業、持倉順序人工覆盤。"


def _evidence_summary(evidence: _EvidenceRead) -> str:
    if evidence.event_count == 0:
        return "尚無完整 cohort identity 的 recommendation_included 事件；不能把零事件當成零風險。"
    window_text = "、".join(
        f"{item.window_days}日 {item.ready} ready/{item.pending}等待/{item.missing}缺件"
        for item in evidence.evidence_windows
    )
    return (
        f"{evidence.event_type} 完整 identity {evidence.event_count} 筆（今日 {evidence.daily_event_count}），"
        f"跳過不完整 identity {evidence.skipped_incomplete_identity} 筆；"
        f"outcome {evidence.outcome_total} 筆：ready {evidence.outcome_ready}、"
        f"等待 {evidence.outcome_pending}、缺件 {evidence.outcome_missing}；各 horizon：{window_text or '未知'}"
    )


def _learning_summary(learning: WorkbenchLearningReceipt | None) -> str:
    if learning is None:
        return "Learning receipt 缺失；不能判定 active model"
    sample = (
        str(learning.natural_matured_sample_count)
        if learning.natural_matured_sample_count is not None
        else "未知"
    )
    candidate_sample = (
        str(learning.candidate_natural_matured_sample_count)
        if learning.candidate_natural_matured_sample_count is not None
        else "未知"
    )
    active_sample = (
        str(learning.active_natural_matured_sample_count)
        if learning.active_natural_matured_sample_count is not None
        else "未知"
    )
    candidate_text = (
        f"candidate={learning.candidate_id}（{learning.candidate_status}）"
        if learning.candidate_id
        else "沒有 candidate"
    )
    return (
        f"Learning {learning.decision}；{candidate_text}；active pointer {learning.active_pointer_status}；"
        f"receipt natural sample {sample}；candidate natural sample {candidate_sample}；"
        f"active natural sample {active_sample}；reason={learning.decision_reason or '未知'}"
    )


def _source_trace(
    *,
    decision_snapshot: DecisionDeskSnapshot | None,
    candidate: _CandidateRead,
    evidence: _EvidenceRead,
    learning: WorkbenchLearningReceipt | None,
) -> tuple[str, ...]:
    trace: list[str] = []
    if decision_snapshot is not None:
        trace.append(f"DecisionDeskSnapshot.as_of_date={decision_snapshot.as_of_date.isoformat()}")
        trace.append(f"DecisionDeskSnapshot.generated_at={decision_snapshot.generated_at.isoformat()}")
        if decision_snapshot.source_lineage:
            trace.append(f"DecisionDeskSnapshot.source_lineage_keys={','.join(sorted(str(key) for key in decision_snapshot.source_lineage))}")
    trace.extend(candidate.source_trace)
    trace.extend(evidence.source_trace)
    if learning is not None:
        trace.extend(learning.source_trace)
    return tuple(dict.fromkeys(trace))


def _summarize_outcomes(
    events: Iterable[EvidenceEvent],
    outcomes: Iterable[EvidenceOutcome],
    windows: tuple[int, ...],
) -> tuple[WorkbenchEvidenceWindow, ...]:
    event_list = tuple(events)
    by_key: dict[tuple[str, int], EvidenceOutcome] = {}
    for outcome in outcomes:
        if outcome.window_days not in windows:
            continue
        key = (str(outcome.event_id), int(outcome.window_days))
        current = by_key.get(key)
        if current is None or _outcome_preference(outcome) < _outcome_preference(current):
            by_key[key] = outcome
    summary: list[WorkbenchEvidenceWindow] = []
    for window in windows:
        ready = pending = missing = 0
        for event in event_list:
            selected_outcome = by_key.get((str(event.event_id), window))
            if selected_outcome is None:
                missing += 1
                continue
            state = _text(
                getattr(selected_outcome.outcome_status, "value", selected_outcome.outcome_status)
            )
            if state == "ready":
                ready += 1
            elif state in {"pending", "insufficient_future_data"}:
                pending += 1
            else:
                missing += 1
        summary.append(
            WorkbenchEvidenceWindow(
                window_days=window,
                total=len(event_list),
                ready=ready,
                pending=pending,
                missing=missing,
            )
        )
    return tuple(summary)


def _outcome_preference(outcome: EvidenceOutcome) -> int:
    state = _text(getattr(outcome.outcome_status, "value", outcome.outcome_status))
    return {"ready": 0, "pending": 1, "insufficient_future_data": 2}.get(state, 3)


def _candidate_reason(row: Mapping[str, Any]) -> str:
    code = _text(row.get("stock_code")) or _text(row.get("證券代號"))
    name = _text(row.get("stock_name")) or _text(row.get("證券名稱"))
    industry = _text(row.get("industry")) or _text(row.get("產業"))
    reason = _text(row.get("recommendation_reason")) or _text(row.get("推薦理由"))
    if not code and not name:
        return ""
    prefix = " ".join(value for value in (code, name) if value)
    parts = [prefix]
    if industry:
        parts.append(f"產業 {industry}")
    if reason:
        parts.append(f"理由 {reason}")
    for key, label in (("總分", "排名分數"), ("score", "排名分數")):
        value = _text(row.get(key))
        if value and not any(label in item for item in parts):
            parts.append(f"{label} {value}")
    return "｜".join(parts)


def _candidate_identity(
    payload: Mapping[str, Any],
    cohort: Mapping[str, Any],
    run_payload: Mapping[str, Any] | None,
    run_context: Mapping[str, Any],
) -> tuple[str, ...]:
    evidence_identity = _mapping(payload.get("evidence_identity"))
    values: list[tuple[str, Any]] = [
        ("strategy_version_id", evidence_identity.get("strategy_version_id") or run_context.get("strategy_version_id")),
        ("strategy_config_id", evidence_identity.get("strategy_config_id") or run_context.get("strategy_config_id")),
        ("universe_policy_id", evidence_identity.get("universe_policy_id") or cohort.get("universe_policy_id")),
        ("universe_policy_hash", evidence_identity.get("universe_policy_hash") or cohort.get("universe_policy_hash")),
        ("universe_snapshot_id", evidence_identity.get("universe_snapshot_id") or cohort.get("universe_snapshot_id")),
        ("universe_snapshot_hash", evidence_identity.get("universe_snapshot_hash") or cohort.get("universe_snapshot_hash")),
        ("cohort_hash", cohort.get("cohort_hash")),
        ("benchmark_id", evidence_identity.get("benchmark_id")),
        ("cost_model_id", evidence_identity.get("cost_model_id")),
        ("cost_scenario_id", evidence_identity.get("cost_scenario_id") or run_context.get("cost_scenario_id")),
        (
            "learning_candidate_id",
            evidence_identity.get("learning_candidate_id")
            or evidence_identity.get("candidate_id")
            or run_context.get("learning_candidate_id")
            or run_context.get("candidate_id")
            or payload.get("learning_candidate_id")
            or payload.get("candidate_id"),
        ),
        ("return_basis", evidence_identity.get("return_basis") or run_context.get("return_basis")),
        ("horizon_days", evidence_identity.get("horizon_days")),
        ("run_context.as_of_date", run_context.get("as_of_date")),
        ("run_context.data_as_of_date", run_context.get("data_as_of_date")),
    ]
    if run_payload is not None and run_payload.get("result_id"):
        values.append(("run.result_id", run_payload.get("result_id")))
    return tuple(f"{key}={_text(value)}" for key, value in values if _text(value))


def _sqlite_table_exists(path: Path, table: str, diagnostics: list[str]) -> bool:
    try:
        with closing(
            connect_read_only_sqlite(path)
        ) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
                (table,),
            ).fetchone()
            check_read_cancelled()
            if row is None:
                diagnostics.append(f"evidence_table_missing:{table}")
            return row is not None
    except (OSError, sqlite3.Error) as exc:
        check_read_cancelled()
        diagnostics.append(f"evidence_db_read_failure:{type(exc).__name__}:{exc}")
        return False


def _read_json_object(path: Path, diagnostics: list[str], source: str) -> dict[str, Any] | None:
    if not path.is_file():
        diagnostics.append(f"{source}_status_missing:{path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        diagnostics.append(f"{source}_read_failure:{type(exc).__name__}")
        return None
    if not isinstance(payload, dict):
        diagnostics.append(f"{source}_payload_not_object")
        return None
    return dict(payload)


def _safe_output_path(root: Path, candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if not resolved.is_relative_to(root.resolve()):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_of_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _date_key(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text[:10]


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(*candidates: tuple[Mapping[str, Any], str]) -> int | None:
    for mapping, key in candidates:
        if key not in mapping or mapping.get(key) is None:
            continue
        parsed = _int_or_none(mapping.get(key))
        if parsed is not None:
            return parsed
    return None


def _int_or_default(value: Any, fallback: int) -> int:
    parsed = _int_or_none(value)
    return fallback if parsed is None else parsed


def _positive_ints(value: Any) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or value is None:
        values: Iterable[Any] = ()
    elif isinstance(value, Iterable):
        values = value
    else:
        values = (value,)
    result: list[int] = []
    for item in values:
        parsed = _int_or_none(item)
        if parsed is not None and parsed > 0 and parsed not in result:
            result.append(parsed)
    return tuple(result) or DEFAULT_WINDOWS


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _bool_or_default(value: Any, fallback: bool) -> bool:
    parsed = _bool_or_none(value)
    return fallback if parsed is None else parsed
