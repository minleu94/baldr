from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app_module.advice_dtos import AdviceDashboardDTO
from app_module.decision_presentation import PositionHealthReadModel
from app_module.machine_status_classification import classify_machine_status

if TYPE_CHECKING:
    from app_module.recommendation_learning_evidence_projection_service import (
        RecommendationLearningEvidenceProjection,
    )


WORKBENCH_LEGACY_DRILLDOWN_TARGETS: dict[str, str] = {
    "daily_decision": "daily_decision",
    "evidence_review": "evidence_review",
    "evidence_mode": "evidence_review",
    "portfolio_review": "portfolio",
    "watchlist": "watchlist",
}


def _normalize_strings(values: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(str(value) for value in values)


def _as_dict(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_as_dict(item) for item in value]
    if isinstance(value, list):
        return [_as_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_dict(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


@dataclass(frozen=True)
class WorkbenchAccessBoundary:
    mode: str = "read_only"
    writes_allowed: bool = False
    production_scheduler_allowed: bool = False
    denied_actions: tuple[str, ...] = (
        "write_database",
        "register_scheduler",
        "place" "_order",
        "adjust_position",
        "apply_lifecycle_action",
        "recalculate_scoring",
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "denied_actions", _normalize_strings(self.denied_actions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "writes_allowed": self.writes_allowed,
            "production_scheduler_allowed": self.production_scheduler_allowed,
            "denied_actions": list(self.denied_actions),
        }


@dataclass(frozen=True)
class WorkbenchStatusItem:
    item_id: str
    label: str
    value: str
    status: str
    summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "value": self.value,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class WorkbenchReviewItem:
    item_id: str
    title: str
    severity: str
    source: str
    summary: str
    drilldown_target: str
    code: str | None = None
    # Continuity review fields are optional so existing non-continuity review
    # rows and positional callers remain compatible.  They are populated only
    # for an exact (result_id, stock_code) reminder projection.
    result_id: str = ""
    stock_code: str = ""
    candidate_key: str = ""
    identity_status: str = "unknown"
    decision_status: str = "unrecorded"
    reminder_status: str = ""
    due_status: str = ""
    next_review_at: str = ""
    recorded_next_review_at: str = ""
    revision_id: str = ""
    reminder_revision_id: str = ""
    revision_of: str = ""
    continuity_event_id: str = ""
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    decision_date: str = ""
    source_trace: str = ""
    note: str = ""
    history_count: int = 0
    diagnostics: tuple[str, ...] = ()
    read_only: bool = True
    writes_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "result_id",
            "stock_code",
            "candidate_key",
            "identity_status",
            "decision_status",
            "reminder_status",
            "due_status",
            "next_review_at",
            "recorded_next_review_at",
            "revision_id",
            "reminder_revision_id",
            "revision_of",
            "continuity_event_id",
            "source_snapshot_id",
            "source_snapshot_hash",
            "decision_date",
            "source_trace",
            "note",
        ):
            object.__setattr__(self, field_name, str(getattr(self, field_name) or "").strip())
        object.__setattr__(self, "decision_status", self.decision_status or "unrecorded")
        object.__setattr__(self, "history_count", max(0, int(self.history_count)))
        object.__setattr__(
            self,
            "diagnostics",
            _normalize_strings(self.diagnostics),
        )
        # Review queue rows are always read-only; no row may opt into writes.
        object.__setattr__(self, "read_only", True)
        object.__setattr__(self, "writes_allowed", False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "severity": self.severity,
            "source": self.source,
            "summary": self.summary,
            "drilldown_target": self.drilldown_target,
            "code": self.code,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "candidate_key": self.candidate_key,
            "identity_status": self.identity_status,
            "decision_status": self.decision_status,
            "reminder_status": self.reminder_status,
            "due_status": self.due_status,
            "next_review_at": self.next_review_at,
            "recorded_next_review_at": self.recorded_next_review_at,
            "revision_id": self.revision_id,
            "reminder_revision_id": self.reminder_revision_id,
            "revision_of": self.revision_of,
            "continuity_event_id": self.continuity_event_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "decision_date": self.decision_date,
            "source_trace": self.source_trace,
            "note": self.note,
            "history_count": self.history_count,
            "diagnostics": list(self.diagnostics),
            "read_only": self.read_only,
            "writes_allowed": self.writes_allowed,
        }


@dataclass(frozen=True)
class WorkbenchEvidenceFeedItem:
    item_id: str
    label: str
    status: str
    summary: str
    source_trace: str
    degraded_reason: str
    drilldown_target: str
    diagnostics: tuple[str, ...] = ()
    status_classification: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))
        classification = str(self.status_classification or "").strip()
        if not classification:
            classification = classify_machine_status(
                self.status,
                (self.degraded_reason, self.summary, *self.diagnostics),
            )
        object.__setattr__(self, "status_classification", classification)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "source_trace": self.source_trace,
            "degraded_reason": self.degraded_reason,
            "drilldown_target": self.drilldown_target,
            "diagnostics": list(self.diagnostics),
            "status_classification": self.status_classification,
        }


@dataclass(frozen=True)
class WorkbenchActionItem:
    item_id: str
    title: str
    source_type: str
    severity: str
    summary: str
    source_trace: str
    degraded_reason: str
    drilldown_target: str
    queue_group: str = "manual_review"
    source_label: str = ""
    sort_rank: int = 9999
    code: str | None = None
    write_intent: bool = False
    status_classification: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "queue_group", str(self.queue_group or "manual_review"))
        object.__setattr__(self, "source_label", str(self.source_label or self.source_type))
        object.__setattr__(self, "sort_rank", int(self.sort_rank))
        classification = str(self.status_classification or "").strip()
        if not classification:
            classification = classify_machine_status(
                self.severity,
                (self.degraded_reason, self.summary, self.title),
            )
        object.__setattr__(self, "status_classification", classification)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "source_type": self.source_type,
            "severity": self.severity,
            "summary": self.summary,
            "source_trace": self.source_trace,
            "degraded_reason": self.degraded_reason,
            "drilldown_target": self.drilldown_target,
            "queue_group": self.queue_group,
            "source_label": self.source_label,
            "sort_rank": self.sort_rank,
            "code": self.code,
            "write_intent": self.write_intent,
            "status_classification": self.status_classification,
        }


@dataclass(frozen=True)
class WorkbenchEvidenceSummary:
    item_id: str
    label: str
    status: str
    summary: str
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class WorkbenchChecklistItem:
    item_id: str
    label: str
    status: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class WorkbenchOperatingLoopStep:
    step_id: str
    label: str
    cadence: str
    status: str
    summary: str
    source_trace: str
    linked_item_ids: tuple[str, ...] = ()
    drilldown_target: str = "evidence_review"
    guidance: str = ""
    write_intent: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "linked_item_ids", _normalize_strings(self.linked_item_ids))
        object.__setattr__(self, "cadence", str(self.cadence or "manual"))
        object.__setattr__(self, "status", str(self.status or "missing"))
        object.__setattr__(self, "guidance", str(self.guidance or ""))
        object.__setattr__(self, "write_intent", bool(self.write_intent))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "cadence": self.cadence,
            "status": self.status,
            "summary": self.summary,
            "source_trace": self.source_trace,
            "linked_item_ids": list(self.linked_item_ids),
            "drilldown_target": self.drilldown_target,
            "guidance": self.guidance,
            "write_intent": self.write_intent,
        }


@dataclass(frozen=True)
class WorkbenchLearningReceipt:
    """唯讀投影：隔離 recommendation learning receipt 的可判讀欄位。"""

    schema_version: str
    status: str
    decision_date: str | None
    checked_at: str | None
    decision: str
    decision_reason: str
    candidate_id: str | None = None
    candidate_status: str = "unknown"
    active_pointer_status: str = "unknown"
    active_candidate_id: str | None = None
    active_effective_date: str | None = None
    active_model_performance_status: str = "unknown"
    active_model_performance_reason: str = ""
    active_natural_evidence_status: str = "unknown"
    active_natural_evidence_reason: str = ""
    natural_matured_sample_count: int | None = None
    natural_matured_decision_date_count: int | None = None
    candidate_natural_matured_sample_count: int | None = None
    candidate_natural_matured_decision_date_count: int | None = None
    active_natural_matured_sample_count: int | None = None
    active_natural_matured_decision_date_count: int | None = None
    shadow_only: bool | None = None
    formal_order_allowed: bool | None = None
    decision_receipt_id: str | None = None
    decision_receipt_hash: str | None = None
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", str(self.schema_version or "unknown"))
        object.__setattr__(self, "status", str(self.status or "unknown"))
        object.__setattr__(self, "decision", str(self.decision or "unknown"))
        object.__setattr__(self, "decision_reason", str(self.decision_reason or ""))
        object.__setattr__(self, "candidate_status", str(self.candidate_status or "unknown"))
        object.__setattr__(self, "active_pointer_status", str(self.active_pointer_status or "unknown"))
        object.__setattr__(self, "active_model_performance_status", str(self.active_model_performance_status or "unknown"))
        object.__setattr__(self, "active_model_performance_reason", str(self.active_model_performance_reason or ""))
        object.__setattr__(self, "active_natural_evidence_status", str(self.active_natural_evidence_status or "unknown"))
        object.__setattr__(self, "active_natural_evidence_reason", str(self.active_natural_evidence_reason or ""))
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))
        object.__setattr__(self, "source_trace", _normalize_strings(self.source_trace))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "decision_date": self.decision_date,
            "checked_at": self.checked_at,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "candidate_id": self.candidate_id,
            "candidate_status": self.candidate_status,
            "active_pointer_status": self.active_pointer_status,
            "active_candidate_id": self.active_candidate_id,
            "active_effective_date": self.active_effective_date,
            "active_model_performance_status": self.active_model_performance_status,
            "active_model_performance_reason": self.active_model_performance_reason,
            "active_natural_evidence_status": self.active_natural_evidence_status,
            "active_natural_evidence_reason": self.active_natural_evidence_reason,
            "natural_matured_sample_count": self.natural_matured_sample_count,
            "natural_matured_decision_date_count": self.natural_matured_decision_date_count,
            "candidate_natural_matured_sample_count": self.candidate_natural_matured_sample_count,
            "candidate_natural_matured_decision_date_count": self.candidate_natural_matured_decision_date_count,
            "active_natural_matured_sample_count": self.active_natural_matured_sample_count,
            "active_natural_matured_decision_date_count": self.active_natural_matured_decision_date_count,
            "shadow_only": self.shadow_only,
            "formal_order_allowed": self.formal_order_allowed,
            "decision_receipt_id": self.decision_receipt_id,
            "decision_receipt_hash": self.decision_receipt_hash,
            "diagnostics": list(self.diagnostics),
            "source_trace": list(self.source_trace),
        }


@dataclass(frozen=True)
class WorkbenchEvidenceWindow:
    """單一 forward horizon 的成熟度分母。"""

    window_days: int
    total: int = 0
    ready: int = 0
    pending: int = 0
    missing: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_days", max(0, int(self.window_days)))
        object.__setattr__(self, "total", max(0, int(self.total)))
        object.__setattr__(self, "ready", max(0, int(self.ready)))
        object.__setattr__(self, "pending", max(0, int(self.pending)))
        object.__setattr__(self, "missing", max(0, int(self.missing)))

    def to_dict(self) -> dict[str, int]:
        return {
            "window_days": self.window_days,
            "total": self.total,
            "ready": self.ready,
            "pending": self.pending,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class ResearchFallbackPacket:
    """Evidence 不足時供 Workbench 閱讀的 bounded research contract。

    這是唯讀呈現 packet，不是第二套 evidence store；只攜帶 scope 與限制，
    不製造機率、score、權重、Advice action 或交易指令。
    """

    status: str
    scope_result_id: str | None = None
    scope_stock_codes: tuple[str, ...] = ()
    decision_date: str | None = None
    cost_lane: str = "unknown"
    source_id: str | None = None
    source_snapshot_id: str | None = None
    source_owner: str = "未知（既有來源未提供 owner）"
    source_owner_known: bool = False
    missing_reason: str = ""
    research_question: str = ""
    next_step: str = ""
    revisit_date: str | None = None
    revisit_status: str = "unknown"
    revisit_basis: str = ""
    revisit_reason: str = ""
    natural_evidence_status: str = "unknown"
    limitations: tuple[str, ...] = ()
    prohibited_actions: tuple[str, ...] = (
        "不可下單、調整持倉或改寫 Portfolio",
        "不可把 historical replay／研究比較當成 natural evidence",
        "不可把 score、權重或 80% 顯示值當成有效機率",
    )
    historical_research_allowed: bool = False
    positive_fallback_allowed: bool = False
    read_only: bool = True
    write_intent: bool = False
    source_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.read_only:
            raise ValueError("research fallback packet must remain read-only")
        if self.positive_fallback_allowed:
            raise ValueError("research fallback packet cannot authorize positive fallback")
        if self.write_intent:
            raise ValueError("research fallback packet cannot carry write intent")
        object.__setattr__(self, "status", str(self.status or "unknown"))
        object.__setattr__(self, "scope_stock_codes", _normalize_strings(self.scope_stock_codes))
        object.__setattr__(self, "cost_lane", str(self.cost_lane or "unknown"))
        object.__setattr__(self, "source_owner", str(self.source_owner or "未知（既有來源未提供 owner）"))
        object.__setattr__(self, "source_owner_known", bool(self.source_owner_known))
        for field_name in (
            "missing_reason",
            "research_question",
            "next_step",
            "revisit_status",
            "revisit_basis",
            "revisit_reason",
            "natural_evidence_status",
        ):
            object.__setattr__(self, field_name, str(getattr(self, field_name) or ""))
        object.__setattr__(self, "limitations", _normalize_strings(self.limitations))
        object.__setattr__(self, "prohibited_actions", _normalize_strings(self.prohibited_actions))
        object.__setattr__(self, "historical_research_allowed", bool(self.historical_research_allowed))
        object.__setattr__(self, "positive_fallback_allowed", False)
        object.__setattr__(self, "read_only", True)
        object.__setattr__(self, "write_intent", False)
        object.__setattr__(self, "source_trace", _normalize_strings(self.source_trace))

    @property
    def scope_key(self) -> str:
        """穩定的呈現／讀取 key；不同日期、來源或成本 scope 絕不合併。"""

        return "|".join(
            (
                self.decision_date or "unknown",
                self.scope_result_id or "unknown",
                ",".join(self.scope_stock_codes) or "unknown",
                self.cost_lane,
                self.source_id or "unknown",
                self.source_snapshot_id or "unknown",
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "scope_key": self.scope_key,
            "scope_result_id": self.scope_result_id,
            "scope_stock_codes": list(self.scope_stock_codes),
            "decision_date": self.decision_date,
            "cost_lane": self.cost_lane,
            "source_id": self.source_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_owner": self.source_owner,
            "source_owner_known": self.source_owner_known,
            "missing_reason": self.missing_reason,
            "research_question": self.research_question,
            "next_step": self.next_step,
            "revisit_date": self.revisit_date,
            "revisit_status": self.revisit_status,
            "revisit_basis": self.revisit_basis,
            "revisit_reason": self.revisit_reason,
            "natural_evidence_status": self.natural_evidence_status,
            "limitations": list(self.limitations),
            "prohibited_actions": list(self.prohibited_actions),
            "historical_research_allowed": self.historical_research_allowed,
            "positive_fallback_allowed": self.positive_fallback_allowed,
            "read_only": self.read_only,
            "write_intent": self.write_intent,
            "source_trace": list(self.source_trace),
        }


@dataclass(frozen=True)
class WorkbenchJourneyStep:
    """市場 → 產業 → 個股 → 觀察清單／持倉的可導覽節點。"""

    step_id: str
    label: str
    status: str
    summary: str
    source_trace: str
    next_action: str = ""
    stock_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", str(self.step_id))
        object.__setattr__(self, "label", str(self.label))
        object.__setattr__(self, "status", str(self.status or "unknown"))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "source_trace", str(self.source_trace))
        object.__setattr__(self, "next_action", str(self.next_action or ""))
        object.__setattr__(self, "stock_codes", _normalize_strings(self.stock_codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "source_trace": self.source_trace,
            "next_action": self.next_action,
            "stock_codes": list(self.stock_codes),
        }


@dataclass(frozen=True)
class WorkbenchDailyEvidence:
    """每日首屏 read model；只接合既有 receipt／snapshot／event 的讀取結果。"""

    status: str
    decision_date: str
    data_as_of_date: str | None
    headline: str
    next_action: str
    market_summary: str
    industry_summary: str
    stock_summary: str
    watchlist_summary: str
    portfolio_summary: str
    candidate_symbols: tuple[str, ...] = ()
    candidate_count: int = 0
    candidate_status: str = "missing"
    candidate_result_id: str | None = None
    candidate_source_id: str | None = None
    candidate_source_snapshot_id: str | None = None
    candidate_data_date: str | None = None
    candidate_quality: str = "missing"
    candidate_requested_count: int | None = None
    candidate_degraded_count: int | None = None
    candidate_missing_count: int | None = None
    candidate_reasons: tuple[str, ...] = ()
    candidate_identity: tuple[str, ...] = ()
    evidence_event_type: str = "recommendation_included"
    evidence_scope_start: str | None = None
    evidence_scope_end: str | None = None
    evidence_require_cohort_identity: bool = True
    evidence_event_count: int = 0
    evidence_daily_event_count: int = 0
    evidence_skipped_incomplete_identity: int = 0
    evidence_event_ids: tuple[str, ...] = ()
    evidence_source_snapshot_ids: tuple[str, ...] = ()
    outcome_total: int = 0
    outcome_ready: int = 0
    outcome_pending: int = 0
    outcome_missing: int = 0
    outcome_windows: tuple[int, ...] = ()
    evidence_windows: tuple[WorkbenchEvidenceWindow, ...] = ()
    learning: WorkbenchLearningReceipt | None = None
    learning_projection: "RecommendationLearningEvidenceProjection | None" = None
    journey_steps: tuple[WorkbenchJourneyStep, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()
    # 追加在 DTO 尾端，以保留舊 positional caller 的相容性。
    research_fallback: ResearchFallbackPacket | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", str(self.status or "unknown"))
        object.__setattr__(self, "decision_date", str(self.decision_date or "unknown"))
        object.__setattr__(self, "headline", str(self.headline))
        object.__setattr__(self, "next_action", str(self.next_action))
        object.__setattr__(self, "market_summary", str(self.market_summary))
        object.__setattr__(self, "industry_summary", str(self.industry_summary))
        object.__setattr__(self, "stock_summary", str(self.stock_summary))
        object.__setattr__(self, "watchlist_summary", str(self.watchlist_summary))
        object.__setattr__(self, "portfolio_summary", str(self.portfolio_summary))
        object.__setattr__(self, "candidate_symbols", _normalize_strings(self.candidate_symbols))
        object.__setattr__(self, "candidate_count", max(0, int(self.candidate_count)))
        object.__setattr__(self, "candidate_status", str(self.candidate_status or "missing"))
        object.__setattr__(self, "candidate_quality", str(self.candidate_quality or "missing"))
        object.__setattr__(self, "candidate_reasons", _normalize_strings(self.candidate_reasons))
        object.__setattr__(self, "candidate_identity", _normalize_strings(self.candidate_identity))
        object.__setattr__(self, "evidence_event_type", str(self.evidence_event_type or "unknown"))
        object.__setattr__(self, "evidence_event_count", max(0, int(self.evidence_event_count)))
        object.__setattr__(self, "evidence_daily_event_count", max(0, int(self.evidence_daily_event_count)))
        object.__setattr__(
            self,
            "evidence_skipped_incomplete_identity",
            max(0, int(self.evidence_skipped_incomplete_identity)),
        )
        object.__setattr__(self, "evidence_event_ids", _normalize_strings(self.evidence_event_ids))
        object.__setattr__(
            self,
            "evidence_source_snapshot_ids",
            _normalize_strings(self.evidence_source_snapshot_ids),
        )
        for field_name in ("outcome_total", "outcome_ready", "outcome_pending", "outcome_missing"):
            object.__setattr__(self, field_name, max(0, int(getattr(self, field_name))))
        object.__setattr__(self, "outcome_windows", tuple(max(0, int(item)) for item in self.outcome_windows))
        object.__setattr__(self, "evidence_windows", tuple(self.evidence_windows))
        object.__setattr__(self, "journey_steps", tuple(self.journey_steps))
        object.__setattr__(self, "warnings", _normalize_strings(self.warnings))
        object.__setattr__(self, "diagnostics", _normalize_strings(self.diagnostics))
        object.__setattr__(self, "source_trace", _normalize_strings(self.source_trace))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision_date": self.decision_date,
            "data_as_of_date": self.data_as_of_date,
            "headline": self.headline,
            "next_action": self.next_action,
            "market_summary": self.market_summary,
            "industry_summary": self.industry_summary,
            "stock_summary": self.stock_summary,
            "watchlist_summary": self.watchlist_summary,
            "portfolio_summary": self.portfolio_summary,
            "candidate_symbols": list(self.candidate_symbols),
            "candidate_count": self.candidate_count,
            "candidate_status": self.candidate_status,
            "candidate_result_id": self.candidate_result_id,
            "candidate_source_id": self.candidate_source_id,
            "candidate_source_snapshot_id": self.candidate_source_snapshot_id,
            "candidate_data_date": self.candidate_data_date,
            "candidate_quality": self.candidate_quality,
            "candidate_requested_count": self.candidate_requested_count,
            "candidate_degraded_count": self.candidate_degraded_count,
            "candidate_missing_count": self.candidate_missing_count,
            "candidate_reasons": list(self.candidate_reasons),
            "candidate_identity": list(self.candidate_identity),
            "evidence_event_type": self.evidence_event_type,
            "evidence_scope_start": self.evidence_scope_start,
            "evidence_scope_end": self.evidence_scope_end,
            "evidence_require_cohort_identity": self.evidence_require_cohort_identity,
            "evidence_event_count": self.evidence_event_count,
            "evidence_daily_event_count": self.evidence_daily_event_count,
            "evidence_skipped_incomplete_identity": self.evidence_skipped_incomplete_identity,
            "evidence_event_ids": list(self.evidence_event_ids),
            "evidence_source_snapshot_ids": list(self.evidence_source_snapshot_ids),
            "outcome_total": self.outcome_total,
            "outcome_ready": self.outcome_ready,
            "outcome_pending": self.outcome_pending,
            "outcome_missing": self.outcome_missing,
            "outcome_windows": list(self.outcome_windows),
            "evidence_windows": [item.to_dict() for item in self.evidence_windows],
            "learning": self.learning.to_dict() if self.learning is not None else None,
            "learning_projection": (
                self.learning_projection.to_dict()
                if self.learning_projection is not None
                else None
            ),
            "research_fallback": (
                self.research_fallback.to_dict()
                if self.research_fallback is not None
                else None
            ),
            "journey_steps": [item.to_dict() for item in self.journey_steps],
            "warnings": list(self.warnings),
            "diagnostics": list(self.diagnostics),
            "source_trace": list(self.source_trace),
        }


@dataclass(frozen=True)
class WorkbenchDashboardDTO:
    as_of_date: date
    generated_at: datetime
    source_mode: str
    access_boundary: WorkbenchAccessBoundary
    status_strip: tuple[WorkbenchStatusItem, ...]
    review_items: tuple[WorkbenchReviewItem, ...]
    evidence_summary: tuple[WorkbenchEvidenceSummary, ...]
    market_context: dict[str, Any]
    portfolio_watchlist_summary: dict[str, Any]
    daily_checklist: tuple[WorkbenchChecklistItem, ...]
    warnings: tuple[str, ...] = ()
    background_evidence_feed: tuple[WorkbenchEvidenceFeedItem, ...] = ()
    action_items: tuple[WorkbenchActionItem, ...] = ()
    operating_loop_steps: tuple[WorkbenchOperatingLoopStep, ...] = ()
    advice_dashboard: AdviceDashboardDTO | None = None
    daily_evidence: WorkbenchDailyEvidence | None = None
    position_health: PositionHealthReadModel | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_strip", tuple(self.status_strip))
        object.__setattr__(self, "review_items", tuple(self.review_items))
        object.__setattr__(self, "evidence_summary", tuple(self.evidence_summary))
        object.__setattr__(self, "daily_checklist", tuple(self.daily_checklist))
        object.__setattr__(self, "warnings", _normalize_strings(self.warnings))
        object.__setattr__(self, "background_evidence_feed", tuple(self.background_evidence_feed))
        object.__setattr__(self, "action_items", tuple(self.action_items))
        object.__setattr__(self, "operating_loop_steps", tuple(self.operating_loop_steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "source_mode": self.source_mode,
            "access_boundary": self.access_boundary.to_dict(),
            "status_strip": [item.to_dict() for item in self.status_strip],
            "review_items": [item.to_dict() for item in self.review_items],
            "evidence_summary": [item.to_dict() for item in self.evidence_summary],
            "market_context": _as_dict(self.market_context),
            "portfolio_watchlist_summary": _as_dict(self.portfolio_watchlist_summary),
            "daily_checklist": [item.to_dict() for item in self.daily_checklist],
            "warnings": list(self.warnings),
            "background_evidence_feed": [item.to_dict() for item in self.background_evidence_feed],
            "action_items": [item.to_dict() for item in self.action_items],
            "operating_loop_steps": [item.to_dict() for item in self.operating_loop_steps],
            "advice_dashboard": (
                self.advice_dashboard.to_dict() if self.advice_dashboard is not None else None
            ),
            "daily_evidence": self.daily_evidence.to_dict() if self.daily_evidence is not None else None,
            "position_health": (
                self.position_health.to_dict()
                if self.position_health is not None
                else None
            ),
        }
