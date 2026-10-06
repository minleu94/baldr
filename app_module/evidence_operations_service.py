from __future__ import annotations

from collections import Counter
from copy import copy, deepcopy
from pathlib import Path
import sqlite3
from typing import Any, Callable

from app_module.decision_quality_service import DecisionQualityService
from app_module.evidence_operations_dtos import (
    EvidenceOperationsActionItemPlan,
    EvidenceOperationsDecisionQuality,
    EvidenceOperationsManualApproval,
    EvidenceOperationsSignalDecay,
    EvidenceOperationsWeeklyReview,
)
from app_module.evidence_scheduler_readiness import evaluate_evidence_scheduler_readiness
from app_module.signal_decay_dtos import SUGGESTION_DEMOTE_CANDIDATE, SUGGESTION_RETIRE_CANDIDATE, SUGGESTION_WATCH
from app_module.signal_decay_service import SignalDecayService
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.live_research_gap_repository import LiveResearchGapRepository
from app_module.signal_decay_repository import SignalDecayRepository
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, StoreIdentity
from app_module.personal_store_selection import resolve_personal_store_selection
from data_module.config import TWStockConfig


ReadinessEvaluator = Callable[..., dict[str, Any]]


class EvidenceOperationsService:
    """Build V1.3 weekly evidence operations reports without applying actions."""

    def __init__(
        self,
        config: TWStockConfig,
        *,
        db_path: str | Path | None = None,
        readiness_evaluator: ReadinessEvaluator = evaluate_evidence_scheduler_readiness,
        decision_quality_service: DecisionQualityService | None = None,
        signal_decay_service: SignalDecayService | None = None,
    ) -> None:
        self.config = config
        self.db_path = Path(db_path) if db_path is not None else Path(config.db_file)
        self.readiness_evaluator = readiness_evaluator
        selection = resolve_personal_store_selection(config)
        self._selected_review_reader = selection.mode is not PersonalStoreMode.LEGACY_COMPAT
        self._review_store_missing = False
        self._market_decay_missing = False
        self._source_lineage: dict[str, Any] = {}
        if self._selected_review_reader:
            route = selection.route(PersonalStoreDomain.REVIEW, StoreIdentity("decision-quality-reviews"))
            self.decision_quality_service = (decision_quality_service if decision_quality_service is not None else
                DecisionQualityService(config, review_route=route, source_db_path=self.db_path, read_only=True))
            if (self.decision_quality_service.review_route != route
                    or self.decision_quality_service.source_db_path != self.db_path):
                raise ValueError("evidence_operations_review_source_route_mismatch")
            self.signal_decay_service = (signal_decay_service if signal_decay_service is not None else
                SignalDecayService(config, db_path=self.db_path,
                    evidence_repository=EvidenceEventRepository(config, db_path=self.db_path, read_only=True),
                    gap_repository=LiveResearchGapRepository(config, db_path=self.db_path, read_only=True),
                    decay_repository=SignalDecayRepository(config, db_path=self.db_path, read_only=True)))
            for repository in (self.signal_decay_service.evidence_repository,
                               self.signal_decay_service.gap_repository,
                               self.signal_decay_service.decay_repository):
                if not repository.read_only or repository.db_path != self.db_path:
                    raise ValueError("evidence_operations_market_readonly_source_required")
        else:
            self.decision_quality_service = decision_quality_service or DecisionQualityService(config, db_path=self.db_path)
            self.signal_decay_service = signal_decay_service or SignalDecayService(config, db_path=self.db_path)

    def build_weekly_review(
        self,
        *,
        start_date: str,
        end_date: str,
        smoke_report_path: str | Path | None = None,
        result_id: str | None = None,
    ) -> EvidenceOperationsWeeklyReview:
        self._source_lineage = {}
        if self._selected_review_reader:
            route = self.decision_quality_service.review_route
            assert route is not None
            self._source_lineage = {"review_store_identity": route.identity.key,
                "review_store_path": str(route.read_source), "market_source_db": str(self.db_path),
                "review_refs": [], "decay_refs": [], "source_snapshot_qualification": "unknown"}
        readiness_payload = self.readiness_evaluator(
            copy(self.config) if self._selected_review_reader else self.config,
            db_path=self.db_path,
            smoke_report_path=smoke_report_path,
            decision_date=end_date,
            result_id=result_id,
        )
        manual_approval = self._manual_approval(readiness_payload)
        dq_summary = self._decision_quality_summary(start_date=start_date, end_date=end_date)
        decay_summary, candidates = self._signal_decay_summary(start_date=start_date, end_date=end_date)
        status = self._status(manual_approval=manual_approval, decision_quality=dq_summary, signal_decay=decay_summary)
        next_actions = self._next_actions(
            status=status,
            manual_approval=manual_approval,
            decision_quality=dq_summary,
            signal_decay=decay_summary,
        )
        warnings = tuple(sorted(set(manual_approval.warnings + manual_approval.blocking_gaps
                                   + (("selected_review_store_missing",) if self._review_store_missing else ())
                                   + (("market_decay_source_missing",) if self._market_decay_missing else ()))))
        return EvidenceOperationsWeeklyReview(
            start_date=start_date,
            end_date=end_date,
            status=status,
            manual_approval=manual_approval,
            decision_quality=dq_summary,
            signal_decay=decay_summary,
            manual_lifecycle_candidates=tuple(candidates),
            next_actions=next_actions,
            warnings=warnings,
            write_performed=False,
        )

    @property
    def source_lineage(self) -> dict[str, Any]:
        """來源引用不等於跨庫 atomic snapshot 或 PIT 資格。"""
        return deepcopy(self._source_lineage)

    def plan_action_items(
        self,
        *,
        start_date: str,
        end_date: str,
        owner: str = "human",
        confirm: bool = False,
    ) -> EvidenceOperationsActionItemPlan:
        reviews = self._selected_reviews(start_date=start_date, end_date=end_date)
        if self._review_store_missing:
            if confirm:
                raise RuntimeError("selected_review_store_missing")
            return EvidenceOperationsActionItemPlan(start_date=start_date, end_date=end_date,
                dry_run=True, open_items_seen=0, action_items_planned=0,
                action_items_created=0, action_items_skipped_existing=0,
                planned_action_items=(), write_performed=False)
        review_ids = {review.review_id for review in reviews}
        open_items = [
            item for item in self.decision_quality_service.list_items(status="open") if item.review_id in review_ids
        ]
        existing_item_ids: set[str] = set()
        for review_id in sorted(review_ids):
            for action in self.decision_quality_service.list_action_items(review_id=review_id):
                if action.item_id:
                    existing_item_ids.add(action.item_id)

        planned: list[dict[str, Any]] = []
        created = 0
        skipped = 0
        for item in open_items:
            if item.item_id in existing_item_ids:
                skipped += 1
                continue
            payload = self._action_payload(item, owner=owner)
            planned.append(payload)
            if confirm:
                self.decision_quality_service.create_action_item(
                    review_id=item.review_id,
                    item_id=item.item_id,
                    description=payload["description"],
                    owner=owner,
                    metadata_json=payload["metadata_json"],
                )
                created += 1
        return EvidenceOperationsActionItemPlan(
            start_date=start_date,
            end_date=end_date,
            dry_run=not confirm,
            open_items_seen=len(open_items),
            action_items_planned=len(planned),
            action_items_created=created,
            action_items_skipped_existing=skipped,
            planned_action_items=tuple(planned),
            write_performed=bool(confirm and created),
        )

    def render_markdown(self, report: EvidenceOperationsWeeklyReview) -> str:
        rows = [
            f"# V1.3 Evidence Operations Weekly Review ({report.start_date} 至 {report.end_date})",
            "",
            f"- status: `{report.status}`",
            f"- scheduler readiness: `{report.manual_approval.readiness}`",
            f"- production scheduler allowed: `{str(report.manual_approval.production_scheduler_allowed).lower()}`",
            f"- decision quality reviews: `{report.decision_quality.reviews_count}`",
            f"- open review items: `{report.decision_quality.open_item_count}`",
            f"- signal decay candidates: `{len(report.manual_lifecycle_candidates)}`",
            "",
            "## Next Actions",
        ]
        rows.extend(f"- `{action}`" for action in report.next_actions)
        rows.extend(["", "## Safety Boundary", "- 本報告只供人工覆盤，不啟用 production scheduler，不自動套用 lifecycle action。"])
        return "\n".join(rows) + "\n"

    @staticmethod
    def _action_payload(item: Any, *, owner: str) -> dict[str, Any]:
        source = item.source_id or item.related_decay_id or item.related_evidence_event_id or item.item_id
        description = f"人工覆盤 {item.item_type}: {source}".strip()
        return {
            "review_id": item.review_id,
            "item_id": item.item_id,
            "description": description,
            "owner": owner,
            "metadata_json": {
                "source": "v1_3_evidence_operations",
                "item_type": item.item_type,
                "related_decay_id": item.related_decay_id,
                "related_evidence_event_id": item.related_evidence_event_id,
                "apply_lifecycle_action": False,
            },
        }

    @staticmethod
    def _manual_approval(payload: dict[str, Any]) -> EvidenceOperationsManualApproval:
        return EvidenceOperationsManualApproval(
            readiness=str(payload.get("readiness") or "not_ready"),
            production_scheduler_allowed=False,
            blocking_gaps=tuple(str(item) for item in payload.get("blocking_gaps", [])),
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            required_manual_checks=tuple(str(item) for item in payload.get("required_manual_checks", [])),
            latest_smoke_status=str(payload.get("latest_smoke_status") or ""),
            working_copy_confirm_passed=bool(payload.get("working_copy_confirm_passed")),
        )

    def _decision_quality_summary(self, *, start_date: str, end_date: str) -> EvidenceOperationsDecisionQuality:
        reviews = self._selected_reviews(start_date=start_date, end_date=end_date)
        if self._review_store_missing:
            return EvidenceOperationsDecisionQuality(reviews_count=0, open_item_count=0, action_item_count=0,
                review_status_counts={}, item_type_counts={}, warnings_count=1)
        if self._selected_review_reader:
            self._source_lineage["review_refs"] = [
                {"review_id": review.review_id, "review_hash": review.review_hash} for review in reviews]
        review_ids = {review.review_id for review in reviews}
        open_items = [
            item for item in self.decision_quality_service.list_items(status="open") if item.review_id in review_ids
        ]
        actions = []
        for review_id in sorted(review_ids):
            actions.extend(self.decision_quality_service.list_action_items(review_id=review_id))
        return EvidenceOperationsDecisionQuality(
            reviews_count=len(reviews),
            open_item_count=len(open_items),
            action_item_count=len(actions),
            review_status_counts=dict(sorted(Counter(review.review_status for review in reviews).items())),
            item_type_counts=dict(sorted(Counter(item.item_type for item in open_items).items())),
            warnings_count=sum(len(review.warnings_json) for review in reviews),
        )

    def _selected_reviews(self, *, start_date: str, end_date: str):
        self._review_store_missing = False
        try:
            return self.decision_quality_service.list_reviews(start_date=start_date, end_date=end_date)
        except (FileNotFoundError, sqlite3.OperationalError) as exc:
            if (not self._selected_review_reader
                    or (not isinstance(exc, FileNotFoundError) and "no such table" not in str(exc).casefold())):
                raise
            self._review_store_missing = True
            return []

    def _signal_decay_summary(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> tuple[EvidenceOperationsSignalDecay, list[dict[str, Any]]]:
        self._market_decay_missing = False
        try:
            source_rows = self.signal_decay_service.list_decay_observations()
        except (FileNotFoundError, sqlite3.OperationalError) as exc:
            if (not self._selected_review_reader
                    or (not isinstance(exc, FileNotFoundError) and "no such table" not in str(exc).casefold())):
                raise
            self._market_decay_missing = True
            return EvidenceOperationsSignalDecay(observations_count=0, demote_candidate_count=0,
                retire_candidate_count=0, watch_count=0, status_counts={"unknown": 1},
                confidence_counts={"unknown": 1}, warnings_count=1), []
        rows = [
            row
            for row in source_rows
            if start_date <= str(row.observation_date)[:10] <= end_date
        ]
        if self._selected_review_reader:
            self._source_lineage["decay_refs"] = [
                {"source_db": str(self.db_path), "decay_id": row.decay_id, "decay_hash": row.decay_hash}
                for row in rows]
        candidates = [
            {
                "decay_id": row.decay_id,
                "observation_date": row.observation_date,
                "signal_scope_type": row.signal_scope_type,
                "signal_scope_id": row.signal_scope_id,
                "suggested_lifecycle_action": row.suggested_lifecycle_action,
                "confidence": row.confidence,
                "quality": row.quality,
                "apply_action": False,
            }
            for row in rows
            if row.suggested_lifecycle_action in {SUGGESTION_DEMOTE_CANDIDATE, SUGGESTION_RETIRE_CANDIDATE}
        ]
        suggestion_counts = Counter(row.suggested_lifecycle_action for row in rows)
        summary = EvidenceOperationsSignalDecay(
            observations_count=len(rows),
            demote_candidate_count=suggestion_counts[SUGGESTION_DEMOTE_CANDIDATE],
            retire_candidate_count=suggestion_counts[SUGGESTION_RETIRE_CANDIDATE],
            watch_count=suggestion_counts[SUGGESTION_WATCH],
            status_counts=dict(sorted(Counter(row.decay_status for row in rows).items())),
            confidence_counts=dict(sorted(Counter(row.confidence for row in rows).items())),
            warnings_count=sum(len(row.warnings_json) for row in rows),
        )
        return summary, candidates

    @staticmethod
    def _status(
        *,
        manual_approval: EvidenceOperationsManualApproval,
        decision_quality: EvidenceOperationsDecisionQuality,
        signal_decay: EvidenceOperationsSignalDecay,
    ) -> str:
        if decision_quality.reviews_count == 0 and signal_decay.observations_count == 0:
            return "coverage_only"
        if (
            manual_approval.blocking_gaps
            or decision_quality.open_item_count
            or signal_decay.demote_candidate_count
            or signal_decay.retire_candidate_count
        ):
            return "needs_manual_review"
        return "ready_for_weekly_closeout"

    @staticmethod
    def _next_actions(
        *,
        status: str,
        manual_approval: EvidenceOperationsManualApproval,
        decision_quality: EvidenceOperationsDecisionQuality,
        signal_decay: EvidenceOperationsSignalDecay,
    ) -> tuple[str, ...]:
        actions: list[str] = []
        if status == "coverage_only":
            actions.append("collect_more_evidence")
        if manual_approval.blocking_gaps:
            actions.append("resolve_scheduler_blocking_gaps")
        if decision_quality.open_item_count:
            actions.append("review_decision_quality_items")
        if decision_quality.action_item_count:
            actions.append("follow_up_open_action_items")
        if signal_decay.demote_candidate_count or signal_decay.retire_candidate_count:
            actions.append("review_signal_decay_candidate")
        if not actions:
            actions.append("prepare_weekly_closeout_note")
        actions.append("keep_production_scheduler_disabled")
        return tuple(dict.fromkeys(actions))
