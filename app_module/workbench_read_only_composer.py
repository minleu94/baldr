from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from app_module.advice_dtos import AdviceDashboardDTO
from app_module.decision_desk_dtos import DecisionDeskSnapshot
from app_module.machine_status_classification import (
    MACHINE_STATUS_HUMAN_REVIEW,
    MACHINE_STATUS_INVALID_EVIDENCE,
    MACHINE_STATUS_MACHINE_CANDIDATE,
    MACHINE_STATUS_MACHINE_DEGRADED,
    MACHINE_STATUS_SOURCE_MISSING,
    MACHINE_STATUS_STALE,
    MACHINE_STATUS_UNKNOWN,
    MACHINE_STATUS_WAITING_FOR_TIME,
    classify_machine_status,
)
from app_module.pre_v2_readiness_service import (
    PreV2ReadinessItem,
    PreV2ReadinessReport,
    STATUS_ACTION_REQUIRED,
    STATUS_WAITING_FOR_TIME,
)
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus
from app_module.continuity_review_projection import (
    CONTINUITY_DUE,
    CONTINUITY_DUE_INVALID,
    CONTINUITY_DUE_OVERDUE,
    CONTINUITY_DUE_SCHEDULED,
    ContinuityReviewProjectionResult,
)
from app_module.workbench_dtos import (
    WorkbenchAccessBoundary,
    WorkbenchActionItem,
    WorkbenchChecklistItem,
    WorkbenchDashboardDTO,
    WorkbenchEvidenceFeedItem,
    WorkbenchEvidenceSummary,
    WorkbenchOperatingLoopStep,
    WorkbenchReviewItem,
    WorkbenchStatusItem,
)


class WorkbenchReadOnlyComposer:
    """Compose the V2.0 Phase 1 workbench payload from read-only inputs."""

    def compose(
        self,
        *,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
        agent_report_sample: dict[str, Any] | None = None,
        scheduled_status: ScheduledEvidenceStatus | None = None,
        historical_replay_summary: dict[str, Any] | None = None,
        source_mode: str = "read_only",
        source_diagnostics: tuple[str, ...] = (),
        advice_dashboard: AdviceDashboardDTO | None = None,
        recommendation_learning_status: dict[str, Any] | None = None,
        continuity_reviews: ContinuityReviewProjectionResult | None = None,
    ) -> WorkbenchDashboardDTO:
        warnings = self._warnings(
            readiness_report,
            agent_report_sample,
            historical_replay_summary,
            source_diagnostics,
            recommendation_learning_status,
        )
        if continuity_reviews is not None:
            warnings.extend(
                f"continuity_review:{item}"
                for item in continuity_reviews.diagnostics
                if str(item).strip()
            )
        if decision_snapshot is not None:
            warnings.extend(item for item in decision_snapshot.warnings if item not in warnings)
        review_items = self._review_items(
            decision_snapshot,
            readiness_report,
            source_diagnostics=source_diagnostics,
            continuity_reviews=continuity_reviews,
        )
        daily_checklist = self._daily_checklist(decision_snapshot, readiness_report)
        background_evidence_feed = self._background_evidence_feed(
            decision_snapshot,
            readiness_report,
            scheduled_status,
            historical_replay_summary,
            recommendation_learning_status,
        )
        action_items = self._action_items(decision_snapshot, readiness_report, historical_replay_summary)
        return WorkbenchDashboardDTO(
            as_of_date=decision_snapshot.as_of_date if decision_snapshot is not None else date.today(),
            generated_at=datetime.utcnow().replace(microsecond=0),
            source_mode=str(source_mode),
            access_boundary=WorkbenchAccessBoundary(),
            status_strip=self._status_strip(decision_snapshot, readiness_report),
            review_items=review_items,
            evidence_summary=self._evidence_summary(
                readiness_report,
                scheduled_status,
                historical_replay_summary,
                recommendation_learning_status,
            ),
            market_context=self._market_context(decision_snapshot),
            portfolio_watchlist_summary=self._portfolio_watchlist_summary(decision_snapshot),
            daily_checklist=daily_checklist,
            warnings=tuple(warnings),
            background_evidence_feed=background_evidence_feed,
            action_items=action_items,
            operating_loop_steps=self._operating_loop_steps(
                review_items=review_items,
                background_evidence_feed=background_evidence_feed,
                action_items=action_items,
                daily_checklist=daily_checklist,
                readiness_report=readiness_report,
                recommendation_learning_status=recommendation_learning_status,
            ),
            advice_dashboard=advice_dashboard,
        )

    def _status_strip(
        self,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
    ) -> tuple[WorkbenchStatusItem, ...]:
        if decision_snapshot is None:
            decision_status = WorkbenchStatusItem(
                item_id="decision_snapshot",
                label="每日決策快照",
                value="missing",
                status="warning",
                summary="缺 Daily Decision durable snapshot；不得讀 UI state 偽造。",
            )
            quality = "missing"
        else:
            quality = decision_snapshot.overall_quality.value
            decision_status = WorkbenchStatusItem(
                item_id="decision_snapshot",
                label="每日決策快照",
                value=decision_snapshot.as_of_date.isoformat(),
                status=quality,
                summary="已讀取 Daily Decision service snapshot。",
            )
        return (
            decision_status,
            WorkbenchStatusItem(
                item_id="data_quality",
                label="資料品質",
                value=quality,
                status=quality,
            ),
            WorkbenchStatusItem(
                item_id="evidence_gate",
                label="證據門檻",
                value=readiness_report.overall_status,
                status=_status_to_severity(readiness_report.overall_status),
                summary=_evidence_gate_status_summary(readiness_report),
            ),
            WorkbenchStatusItem(
                item_id="scheduler",
                label="正式排程器",
                value="off",
                status="blocked",
                summary="Phase 5 approval 前固定維持 write-mode off。",
            ),
        )

    def _review_items(
        self,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
        *,
        source_diagnostics: tuple[str, ...] = (),
        continuity_reviews: ContinuityReviewProjectionResult | None = None,
    ) -> tuple[WorkbenchReviewItem, ...]:
        items: list[WorkbenchReviewItem] = []
        if continuity_reviews is not None:
            items.extend(self._continuity_review_items(continuity_reviews))
        source_gap_item = _source_diagnostic_review_item(source_diagnostics)
        if source_gap_item is not None:
            items.append(source_gap_item)
        if decision_snapshot is not None:
            watchlist = decision_snapshot.watchlist_triggers
            if (watchlist.trigger_count or 0) > 0 or watchlist.triggered_codes:
                items.append(
                    WorkbenchReviewItem(
                        item_id="watchlist_trigger",
                        title="觀察清單觸發覆盤",
                        severity="info",
                        source="watchlist_trigger",
                        summary=f"候選池觸發 {watchlist.trigger_count or len(watchlist.triggered_codes)} 筆，需要人工判讀。",
                        drilldown_target="evidence_mode",
                    )
                )
            portfolio = decision_snapshot.portfolio_alerts
            if (portfolio.alert_count or 0) > 0 or portfolio.alert_codes:
                items.append(
                    WorkbenchReviewItem(
                        item_id="portfolio_alert",
                        title="持倉警示覆盤",
                        severity="warning",
                        source="portfolio_alert",
                        summary=f"持倉警示 {portfolio.alert_count or len(portfolio.alert_codes)} 筆，需檢查 thesis 與風險來源。",
                        drilldown_target="portfolio_review",
                    )
                )
            for index, prompt in enumerate(decision_snapshot.risk_prompts.prompts, start=1):
                items.append(
                    WorkbenchReviewItem(
                        item_id=f"risk_prompt_{index}",
                        title=prompt.title,
                        severity=_severity(prompt.severity),
                        source="risk_prompt",
                        summary=prompt.reason,
                        drilldown_target="evidence_mode",
                        code=prompt.code,
                    )
                )
        for item in readiness_report.items:
            classification = _readiness_status_classification(item)
            if (
                item.status in {STATUS_ACTION_REQUIRED, STATUS_WAITING_FOR_TIME}
                and classification == MACHINE_STATUS_HUMAN_REVIEW
            ):
                items.append(
                    WorkbenchReviewItem(
                        item_id=f"readiness_{item.item_id}",
                        title=item.label,
                        severity=_status_to_severity(item.status),
                        source="pre_v2_readiness",
                        summary=(
                            f"{_readiness_summary(item.observed_count, item.required_count)}；"
                            "此項有明確人工判讀需求。"
                        ),
                        drilldown_target="evidence_mode",
                    )
                )
        return tuple(items)

    @staticmethod
    def _continuity_review_items(
        projection: ContinuityReviewProjectionResult,
    ) -> tuple[WorkbenchReviewItem, ...]:
        """Map exact Journal reminders into the existing read-only queue."""

        result: list[WorkbenchReviewItem] = []
        for item in projection.items:
            due_status = item.due_status
            severity = {
                CONTINUITY_DUE_OVERDUE: "critical",
                CONTINUITY_DUE: "warning",
                CONTINUITY_DUE_INVALID: "critical",
            }.get(due_status, "info")
            next_review = item.next_review_at or item.recorded_next_review_at or "無效／未提供"
            decision_text = {
                "accepted": "已納入研究",
                "skipped": "已略過",
                "unrecorded": "尚未記錄",
            }.get(item.decision_status, "狀態未知")
            reason_text = {
                CONTINUITY_DUE_OVERDUE: "已逾期，應優先檢討",
                CONTINUITY_DUE: "已到檢討時間",
                CONTINUITY_DUE_INVALID: "檢討時間無效，需人工確認",
                CONTINUITY_DUE_SCHEDULED: "尚未到檢討時間",
            }.get(due_status, "尚未形成可用檢討提醒")
            result.append(
                WorkbenchReviewItem(
                    item_id=f"continuity_review:{item.result_id}:{item.stock_code}",
                    title=f"研究檢討提醒｜{item.stock_code}",
                    severity=severity,
                    source="continuity_review",
                    summary=(
                        f"股票 {item.stock_code}｜研究意向：{decision_text}｜"
                        f"檢討時間（台北）：{next_review}｜待檢討原因：{reason_text}。"
                    ),
                    drilldown_target="stock_research",
                    code=item.stock_code,
                    result_id=item.result_id,
                    stock_code=item.stock_code,
                    candidate_key=item.candidate_key_text,
                    identity_status=item.identity_status,
                    decision_status=item.decision_status,
                    reminder_status=item.reminder_status,
                    due_status=item.due_status,
                    next_review_at=item.next_review_at,
                    recorded_next_review_at=item.recorded_next_review_at,
                    revision_id=item.revision_id,
                    reminder_revision_id=item.reminder_revision_id,
                    revision_of=item.revision_of,
                    continuity_event_id=item.continuity_event_id,
                    source_snapshot_id=item.source_snapshot_id,
                    source_snapshot_hash=item.source_snapshot_hash,
                    decision_date=item.decision_date,
                    source_trace=item.source_trace,
                    note=item.note,
                    history_count=item.history_count,
                    diagnostics=item.diagnostics,
                )
            )
        return tuple(result)

    def _background_evidence_feed(
        self,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
        scheduled_status: ScheduledEvidenceStatus | None,
        historical_replay_summary: dict[str, Any] | None,
        recommendation_learning_status: dict[str, Any] | None = None,
    ) -> tuple[WorkbenchEvidenceFeedItem, ...]:
        items: list[WorkbenchEvidenceFeedItem] = []
        if decision_snapshot is None:
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="daily_decision_snapshot",
                    label="Daily Decision snapshot",
                    status="missing",
                    summary="缺 Daily Decision durable snapshot；Workbench 不讀 UI state 補值。",
                    source_trace="DecisionDeskSnapshot",
                    degraded_reason="decision_desk_snapshot_missing",
                    drilldown_target="daily_decision",
                )
            )
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="portfolio_alerts",
                    label="Portfolio alerts",
                    status="missing",
                    summary="缺 Daily Decision snapshot，因此沒有既有 portfolio alert payload 可呈現。",
                    source_trace="DecisionDeskSnapshot.portfolio_alerts",
                    degraded_reason="decision_desk_snapshot_missing",
                    drilldown_target="portfolio_review",
                )
            )
        else:
            portfolio = decision_snapshot.portfolio_alerts
            risk_prompt_count = len(decision_snapshot.risk_prompts.prompts)
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="daily_decision_snapshot",
                    label="Daily Decision snapshot",
                    status=decision_snapshot.overall_quality.value,
                    summary=(
                        f"as_of={decision_snapshot.as_of_date.isoformat()}；"
                        f"watchlist={portfolio_safe_count(decision_snapshot.watchlist_triggers.trigger_count, decision_snapshot.watchlist_triggers.triggered_codes)}；"
                        f"portfolio_alerts={portfolio_safe_count(portfolio.alert_count, portfolio.alert_codes)}；"
                        f"risk_prompts={risk_prompt_count}。"
                    ),
                    source_trace="DecisionDeskSnapshot",
                    degraded_reason=_reason_or_none(decision_snapshot.warnings),
                    drilldown_target="daily_decision",
                    diagnostics=decision_snapshot.warnings,
                )
            )
            portfolio_diagnostics = (
                *portfolio.warnings,
                *(flag for attribution in portfolio.attributions for flag in attribution.data_quality_flags),
            )
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="portfolio_alerts",
                    label="Portfolio alerts",
                    status=portfolio.quality.value,
                    summary=(
                        f"{portfolio_safe_count(portfolio.alert_count, portfolio.alert_codes)} alert rows；"
                        f"level={portfolio.alert_level or 'n/a'}。"
                    ),
                    source_trace="DecisionDeskSnapshot.portfolio_alerts",
                    degraded_reason=_reason_or_none(portfolio_diagnostics),
                    drilldown_target="portfolio_review",
                    diagnostics=tuple(str(item) for item in portfolio_diagnostics),
                )
            )

        items.append(
            WorkbenchEvidenceFeedItem(
                item_id="evidence_review_readiness",
                label="Evidence Review readiness",
                status=readiness_report.overall_status,
                summary=_readiness_feed_summary(readiness_report),
                source_trace="PreV2ReadinessReport",
                degraded_reason=_readiness_reason(readiness_report),
                drilldown_target="evidence_review",
                diagnostics=tuple(
                    reason
                    for item in readiness_report.items
                    for reason in (*item.blocking_reasons, *item.diagnostics)
                ),
                status_classification=_readiness_report_classification(readiness_report),
            )
        )
        if scheduled_status is not None:
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="scheduled_morning_pipeline",
                    label="Scheduled morning pipeline",
                    status=_scheduled_status_label(scheduled_status),
                    summary=_scheduled_status_summary(scheduled_status),
                    source_trace="ScheduledEvidenceStatusService",
                    degraded_reason=_reason_or_none(scheduled_status.diagnostics),
                    drilldown_target="evidence_review",
                    diagnostics=scheduled_status.diagnostics,
                    status_classification=scheduled_status.machine_status_classification,
                )
            )

        if recommendation_learning_status is not None:
            items.append(_recommendation_learning_feed_item(recommendation_learning_status))

        if historical_replay_summary:
            diagnostics = _replay_diagnostics(historical_replay_summary)
            final = historical_replay_summary.get("final_outcome_summary", {})
            missing_industry = _int(final.get("missing_industry_benchmark"))
            pending_future = _int(final.get("pending_insufficient_future_data"))
            source_gap_count = sum(1 for item in diagnostics if item.startswith("source_gap:"))
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="replay_summary_diagnostics",
                    label="Replay summary diagnostics",
                    status="degraded" if missing_industry or pending_future or source_gap_count else "ready",
                    summary=(
                        "Historical replay JSON summary 已揭露 "
                        f"source_gaps={source_gap_count}；missing_industry={missing_industry}；"
                        f"pending_future_data={pending_future}。"
                    ),
                    source_trace="HistoricalReplaySummary",
                    degraded_reason=_reason_or_none(
                        tuple(item for item in diagnostics if item.startswith(("source_gap:", "payload_gap:", "missing_", "pending_")))
                    ),
                    drilldown_target="evidence_review",
                    diagnostics=tuple(diagnostics),
                )
            )
        else:
            items.append(
                WorkbenchEvidenceFeedItem(
                    item_id="replay_summary_diagnostics",
                    label="Replay summary diagnostics",
                    status="missing",
                    summary="未提供 replay JSON summary；Workbench 不讀 replay DB、不執行 replay。",
                    source_trace="HistoricalReplaySummary",
                    degraded_reason="replay_summary_not_supplied",
                    drilldown_target="evidence_review",
                )
            )
        return tuple(items)

    def _action_items(
        self,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
        historical_replay_summary: dict[str, Any] | None,
    ) -> tuple[WorkbenchActionItem, ...]:
        items: list[WorkbenchActionItem] = []
        if decision_snapshot is not None:
            watchlist = decision_snapshot.watchlist_triggers
            watchlist_count = portfolio_safe_count(watchlist.trigger_count, watchlist.triggered_codes)
            if watchlist_count > 0:
                severity = "info"
                queue_group = "daily_review"
                source_type = "watchlist_trigger"
                items.append(
                    WorkbenchActionItem(
                        item_id="watchlist_trigger_manual_review",
                        title="觀察清單觸發人工覆盤",
                        source_type=source_type,
                        severity=severity,
                        summary=f"既有 snapshot 顯示 {watchlist_count} 筆觀察清單觸發，需人工判讀。",
                        source_trace="DecisionDeskSnapshot.watchlist_triggers",
                        degraded_reason=_reason_or_none(watchlist.warnings, "watchlist_trigger_requires_manual_review"),
                        drilldown_target="daily_decision",
                        queue_group=queue_group,
                        source_label="觀察清單觸發",
                        sort_rank=_action_sort_rank(severity, queue_group, source_type, len(items)),
                        code=", ".join(watchlist.triggered_codes) or None,
                    )
                )
            portfolio = decision_snapshot.portfolio_alerts
            portfolio_count = portfolio_safe_count(portfolio.alert_count, portfolio.alert_codes)
            if portfolio_count > 0:
                severity = "warning"
                queue_group = "portfolio_review"
                source_type = "portfolio_alert"
                items.append(
                    WorkbenchActionItem(
                        item_id="portfolio_alert_manual_review",
                        title="持倉警示人工覆盤",
                        source_type=source_type,
                        severity=severity,
                        summary=f"既有 snapshot 顯示 {portfolio_count} 筆持倉警示，需檢查 thesis 與風險來源。",
                        source_trace="DecisionDeskSnapshot.portfolio_alerts",
                        degraded_reason=_reason_or_none(portfolio.warnings, "portfolio_alert_requires_manual_review"),
                        drilldown_target="portfolio_review",
                        queue_group=queue_group,
                        source_label="持倉警示",
                        sort_rank=_action_sort_rank(severity, queue_group, source_type, len(items)),
                        code=", ".join(portfolio.alert_codes) or None,
                    )
                )
            for index, prompt in enumerate(decision_snapshot.risk_prompts.prompts, start=1):
                severity = _severity(prompt.severity)
                queue_group = "daily_review"
                source_type = "risk_prompt"
                items.append(
                    WorkbenchActionItem(
                        item_id=f"risk_prompt_manual_review_{index}",
                        title=prompt.title,
                        source_type=source_type,
                        severity=severity,
                        summary=prompt.action_hint,
                        source_trace=f"DecisionDeskSnapshot.risk_prompts[{index}].{prompt.source}",
                        degraded_reason=prompt.reason,
                        drilldown_target="daily_decision",
                        queue_group=queue_group,
                        source_label="風險提示",
                        sort_rank=_action_sort_rank(severity, queue_group, source_type, len(items)),
                        code=prompt.code,
                    )
                )

        for readiness_item in readiness_report.items:
            if readiness_item.status not in {STATUS_ACTION_REQUIRED, STATUS_WAITING_FOR_TIME}:
                continue
            severity = _status_to_severity(readiness_item.status)
            queue_group = "evidence_gate"
            source_type = "pre_v2_readiness"
            status_classification = _readiness_status_classification(readiness_item)
            items.append(
                WorkbenchActionItem(
                    item_id=f"readiness_{readiness_item.item_id}",
                    title=readiness_item.label,
                    source_type=source_type,
                    severity=severity,
                    summary=_readiness_summary(readiness_item.observed_count, readiness_item.required_count),
                    source_trace=f"PreV2ReadinessReport.items.{readiness_item.item_id}",
                    degraded_reason=_reason_or_none(
                        (*readiness_item.blocking_reasons, *readiness_item.diagnostics, *readiness_item.next_actions),
                        readiness_item.status,
                    ),
                    drilldown_target="evidence_review",
                    queue_group=queue_group,
                    source_label="Pre-V2 準備度",
                    sort_rank=_action_sort_rank(severity, queue_group, source_type, len(items)),
                    status_classification=status_classification,
                )
            )

        if historical_replay_summary:
            diagnostics = tuple(
                item
                for item in _replay_diagnostics(historical_replay_summary)
                if item.startswith(("source_gap:", "payload_gap:", "missing_", "pending_", "phase0_gate_not_satisfied:"))
            )
            if diagnostics:
                severity = "info"
                queue_group = "replay_diagnostics"
                source_type = "replay_summary"
                items.append(
                    WorkbenchActionItem(
                        item_id="replay_summary_manual_review",
                        title="Replay summary gap 人工判讀",
                        source_type=source_type,
                        severity=severity,
                        summary="Replay summary 只揭露 simulated evidence gap，不解除 Phase 0 gate。",
                        source_trace="HistoricalReplaySummary.quality_disclosures",
                        degraded_reason="; ".join(diagnostics),
                        drilldown_target="evidence_review",
                        queue_group=queue_group,
                        source_label="Replay summary",
                        sort_rank=_action_sort_rank(severity, queue_group, source_type, len(items)),
                    )
                )
        return tuple(sorted(items, key=lambda item: (item.sort_rank, item.item_id)))

    def _evidence_summary(
        self,
        readiness_report: PreV2ReadinessReport,
        scheduled_status: ScheduledEvidenceStatus | None,
        historical_replay_summary: dict[str, Any] | None,
        recommendation_learning_status: dict[str, Any] | None = None,
    ) -> tuple[WorkbenchEvidenceSummary, ...]:
        items = [
            WorkbenchEvidenceSummary(
                item_id=item.item_id,
                label=item.label,
                status=item.status,
                summary=_readiness_summary(item.observed_count, item.required_count),
                diagnostics=(*item.blocking_reasons, *item.diagnostics),
            )
            for item in readiness_report.items
        ]
        if scheduled_status is not None:
            items.append(
                WorkbenchEvidenceSummary(
                    item_id="scheduled_morning_pipeline",
                    label="每日排程觀測",
                    status=_scheduled_status_label(scheduled_status),
                    summary=_scheduled_status_summary(scheduled_status),
                    diagnostics=scheduled_status.diagnostics,
                )
            )
        if recommendation_learning_status is not None:
            status = _recommendation_learning_payload(recommendation_learning_status)
            items.append(
                WorkbenchEvidenceSummary(
                    item_id="recommendation_learning",
                    label="每日推薦學習與受控調整",
                    status=status["status"],
                    summary=status["summary"],
                    diagnostics=status["diagnostics"],
                )
            )
        if historical_replay_summary:
            totals = historical_replay_summary.get("totals", {})
            final = historical_replay_summary.get("final_outcome_summary", {})
            missing_benchmark = int(final.get("missing_benchmark", 0) or 0)
            missing_industry = int(final.get("missing_industry_benchmark", 0) or 0)
            benchmark_text = "市場 benchmark 已可用" if missing_benchmark == 0 else "市場 benchmark 有缺口"
            quality_disclosures = tuple(
                str(item) for item in historical_replay_summary.get("quality_disclosures", ())
            )
            diagnostics = _dedupe(
                [
                    *quality_disclosures,
                    *(str(item) for item in historical_replay_summary.get("warnings", ())),
                    *(str(item) for item in historical_replay_summary.get("limitations", ())),
                ]
            )
            items.append(
                WorkbenchEvidenceSummary(
                    item_id="historical_replay",
                    label="歷史 replay 模擬證據",
                    status="degraded" if missing_industry else "ready",
                    summary=(
                        f"{totals.get('days', 0)} 天 / {totals.get('events_seen', 0)} events / "
                        f"{totals.get('outcomes_created', 0)} outcomes；{benchmark_text}；"
                        f"產業基準缺口 {missing_industry}。"
                    ),
                    diagnostics=tuple(diagnostics),
                )
            )
        return tuple(items)

    def _operating_loop_steps(
        self,
        *,
        review_items: tuple[WorkbenchReviewItem, ...],
        background_evidence_feed: tuple[WorkbenchEvidenceFeedItem, ...],
        action_items: tuple[WorkbenchActionItem, ...],
        daily_checklist: tuple[WorkbenchChecklistItem, ...],
        readiness_report: PreV2ReadinessReport,
        recommendation_learning_status: dict[str, Any] | None = None,
    ) -> tuple[WorkbenchOperatingLoopStep, ...]:
        weekly_history = _find_readiness_item(readiness_report, "weekly_history")
        multi_day = _find_readiness_item(readiness_report, "multi_day_dry_run")
        manual_note = _find_checklist_item(daily_checklist, "manual_review_note")
        human_action_items = tuple(
            item for item in action_items if _action_requires_human_review(item)
        )
        machine_action_items = tuple(
            item for item in action_items if not _action_requires_human_review(item)
        )
        first_action_target = (
            human_action_items[0].drilldown_target
            if human_action_items
            else machine_action_items[0].drilldown_target
            if machine_action_items
            else "evidence_review"
        )
        steps = [
            WorkbenchOperatingLoopStep(
                step_id="daily_start",
                label="每日先看",
                cadence="daily",
                status="manual_required" if review_items else "observed",
                summary=(
                    f"今天要看 {len(review_items)} 筆今日待判讀與 "
                    f"{len(background_evidence_feed)} 筆背景證據；只讀，不寫 DB。"
                ),
                source_trace="WorkbenchDashboardDTO.review_items",
                linked_item_ids=tuple(item.item_id for item in review_items),
                drilldown_target="daily_decision" if review_items else "evidence_review",
                guidance="先掃 status strip、今日待判讀、背景證據流與 warnings；不是買賣建議。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="manual_queue",
                label="人工與機器處理佇列",
                cadence="daily",
                status="manual_required" if human_action_items else "observed",
                summary=(
                    f"目前有 {len(human_action_items)} 筆 Action Items 要人工處理；"
                    f"另有 {len(machine_action_items)} 筆機器證據狀態，無需人工簽核。"
                    "只依 source trace / degraded reason 覆盤，不標記完成。"
                ),
                source_trace="WorkbenchDashboardDTO.action_items",
                linked_item_ids=tuple(item.item_id for item in action_items),
                drilldown_target=first_action_target,
                guidance="依 severity、queue group 與 source label 掃描；Workbench 不建立 repository。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="weekly_review_history",
                label="Weekly review history",
                cadence="weekly_until_3",
                status=weekly_history.status if weekly_history is not None else "missing",
                summary=_operating_loop_readiness_summary(weekly_history),
                source_trace="PreV2ReadinessReport.items.weekly_history",
                linked_item_ids=("weekly_history",),
                drilldown_target="evidence_review",
                guidance="每週 evidence operations + history 必須靠真實週期累積。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="multi_day_dry_run",
                label="Multi-day dry-run",
                cadence="daily_until_3",
                status=multi_day.status if multi_day is not None else "missing",
                summary=_operating_loop_readiness_summary(multi_day),
                source_trace="PreV2ReadinessReport.items.multi_day_dry_run",
                linked_item_ids=("multi_day_dry_run",),
                drilldown_target="evidence_review",
                guidance="多日 dry-run 必須靠真實交易日紀錄累積；不執行 replay 補值。",
            ),
        ]
        if recommendation_learning_status is not None:
            learning = _recommendation_learning_payload(recommendation_learning_status)
            steps.append(
                WorkbenchOperatingLoopStep(
                    step_id="daily_recommendation_learning",
                    label="每日推薦學習閉環",
                    cadence="daily_after_maturity",
                    status=learning["status"],
                    summary=learning["summary"],
                    source_trace="DailyRecommendationLearningRunner.latest_status",
                    linked_item_ids=("recommendation_learning",),
                    drilldown_target="evidence_review",
                    guidance=learning["next_step"],
                )
            )
        steps.extend([
            WorkbenchOperatingLoopStep(
                step_id="manual_review_note",
                label="人工覆盤註記",
                cadence="after_manual_review",
                status=manual_note.status if manual_note is not None else "manual_required",
                summary=(
                    "人工覆盤後只提示到既有流程留下 note；"
                    "Workbench 不寫 DB、不標記完成、不套用 lifecycle。"
                ),
                source_trace="WorkbenchDashboardDTO.daily_checklist.manual_review_note",
                linked_item_ids=("manual_review_note",),
                drilldown_target="evidence_review",
                guidance="需要紀錄時下鑽到既有 Evidence Review / Daily Decision 流程人工處理。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="scheduler_gate",
                label="Scheduler gate",
                cadence="phase_gate",
                status="blocked",
                summary="production_scheduler_allowed=false；Phase 0 / Phase 5 gate 前不啟用 scheduler。",
                source_trace="WorkbenchAccessBoundary.production_scheduler_allowed",
                linked_item_ids=("scheduler_off",),
                drilldown_target="evidence_review",
                guidance="這是 closeout guard，不是啟用排程或交易建議。",
            ),
        ])
        return tuple(steps)

    def _market_context(self, decision_snapshot: DecisionDeskSnapshot | None) -> dict[str, Any]:
        if decision_snapshot is None:
            return {"source_status": "missing"}
        return {
            "source_status": "ready",
            "overall_quality": decision_snapshot.overall_quality.value,
            "market_regime": decision_snapshot.market_regime.to_dict(),
            "market_breadth": decision_snapshot.market_breadth.to_dict(),
            "sector_rotation": decision_snapshot.sector_rotation.to_dict(),
            "relative_strength_liquidity": decision_snapshot.relative_strength_liquidity.to_dict(),
            "recommendations": decision_snapshot.recommendations.to_dict() if decision_snapshot.recommendations else None,
            "source_lineage": decision_snapshot.source_lineage,
        }

    def _portfolio_watchlist_summary(self, decision_snapshot: DecisionDeskSnapshot | None) -> dict[str, Any]:
        if decision_snapshot is None:
            return {"source_status": "missing"}
        return {
            "source_status": "ready",
            "watchlist_triggers": decision_snapshot.watchlist_triggers.to_dict(),
            "portfolio_alerts": decision_snapshot.portfolio_alerts.to_dict(),
        }

    def _daily_checklist(
        self,
        decision_snapshot: DecisionDeskSnapshot | None,
        readiness_report: PreV2ReadinessReport,
    ) -> tuple[WorkbenchChecklistItem, ...]:
        return (
            WorkbenchChecklistItem(
                item_id="freshness",
                label="決策快照新鮮度",
                status="done" if decision_snapshot is not None else "blocked",
                summary="已讀取 snapshot。" if decision_snapshot is not None else "缺 snapshot；不可從 UI state 補值。",
            ),
            WorkbenchChecklistItem(
                item_id="evidence_gate",
                label="證據門檻狀態",
                status=readiness_report.overall_status,
                summary=f"Pre-V2 readiness：{readiness_report.overall_status}",
            ),
            WorkbenchChecklistItem(
                item_id="multi_day_dry_run",
                label="多日 dry-run",
                status=_find_status(readiness_report, "multi_day_dry_run"),
                summary="真實多日 dry-run 仍需依記錄累積。",
            ),
            WorkbenchChecklistItem(
                item_id="manual_review_note",
                label="人工覆盤註記",
                status="manual_required",
                summary="Phase 1 prototype 不新增 append-only manual note repository。",
            ),
            WorkbenchChecklistItem(
                item_id="scheduler_off",
                label="排程器寫入模式",
                status="blocked",
                summary="production_scheduler_allowed=false；不是交易建議。",
            ),
        )

    def _warnings(
        self,
        readiness_report: PreV2ReadinessReport,
        agent_report_sample: dict[str, Any] | None,
        historical_replay_summary: dict[str, Any] | None,
        source_diagnostics: tuple[str, ...] = (),
        recommendation_learning_status: dict[str, Any] | None = None,
    ) -> list[str]:
        warnings = [
            "Phase 1 prototype 為 research/read-only 模式，不是交易建議。",
            "waiting_for_time 不能用單次 smoke 取代。",
            *readiness_report.limitations,
            *source_diagnostics,
        ]
        # 將 readiness 的具體 blocker/diagnostic 帶到首頁 warnings，避免
        # 使用者只看到「等待中」卻不知道缺哪一份證據或設定。
        for item in readiness_report.items:
            warnings.extend(
                f"{item.item_id}:{reason}"
                for reason in (*item.blocking_reasons, *item.diagnostics)
                if str(reason).strip()
            )
        if agent_report_sample:
            warnings.extend(str(item) for item in agent_report_sample.get("warnings", ()))
            warnings.extend(str(item) for item in agent_report_sample.get("limitations", ()))
        if historical_replay_summary:
            warnings.extend(
                (
                    "historical_replay / simulated_scheduler 只作 V2.0 設計輸入。",
                    "historical replay 不滿足 Phase 0 weekly / multi-day gate。",
                )
            )
            warnings.extend(str(item) for item in historical_replay_summary.get("warnings", ()))
        if recommendation_learning_status is not None:
            warnings.extend(_recommendation_learning_payload(recommendation_learning_status)["diagnostics"])
        return _dedupe(warnings)


def portfolio_safe_count(count: int | None, codes: tuple[str, ...]) -> int:
    return int(count if count is not None else len(codes))


def _readiness_feed_summary(readiness_report: PreV2ReadinessReport) -> str:
    parts = [f"overall={readiness_report.overall_status}"]
    for item in readiness_report.items:
        if item.required_count is not None:
            parts.append(f"{item.item_id}={item.observed_count or 0}/{item.required_count}")
        else:
            parts.append(f"{item.item_id}={item.status}")
    return "；".join(parts) + "。"


def _readiness_reason(readiness_report: PreV2ReadinessReport) -> str:
    reasons = tuple(
        reason
        for item in readiness_report.items
        if item.status in {STATUS_ACTION_REQUIRED, STATUS_WAITING_FOR_TIME}
        for reason in (*item.blocking_reasons, *item.diagnostics)
    )
    return _reason_or_none(reasons, readiness_report.overall_status)


def _replay_diagnostics(historical_replay_summary: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *(str(item) for item in historical_replay_summary.get("quality_disclosures", ())),
            *(str(item) for item in historical_replay_summary.get("warnings", ())),
            *(str(item) for item in historical_replay_summary.get("limitations", ())),
        ]
    )


def _reason_or_none(values: tuple[str, ...] | list[str] | set[str], fallback: str = "none") -> str:
    clean = tuple(str(item) for item in values if str(item))
    if clean:
        return "; ".join(clean)
    return fallback


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _recommendation_learning_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the runner's latest status for read-only Workbench display."""

    decision_receipt = payload.get("decision_receipt")
    receipt = decision_receipt if isinstance(decision_receipt, Mapping) else {}
    raw_status = str(payload.get("status") or "unknown").strip().lower()
    decision = str(payload.get("decision") or receipt.get("decision") or "retain_current")
    reason = str(
        payload.get("decision_reason")
        or receipt.get("reason")
        or payload.get("reason")
        or "recommendation_learning_status_missing_reason"
    )
    matured = _int(
        payload.get(
            "natural_matured_sample_count",
            receipt.get("natural_matured_sample_count", 0),
        )
    )
    active_evidence = payload.get("active_model_natural_evidence")
    active_evidence = active_evidence if isinstance(active_evidence, Mapping) else {}
    active_matured = _int(active_evidence.get("matured_sample_count", 0))
    active_matured_dates = _int(active_evidence.get("matured_unique_decision_date_count", 0))
    dependencies = payload.get("dependencies")
    dependencies = dependencies if isinstance(dependencies, Mapping) else {}
    source_contract = dependencies.get("source_contract")
    source_contract = source_contract if isinstance(source_contract, Mapping) else {}
    source_contract_lanes = source_contract.get("lanes")
    source_contract_lanes = source_contract_lanes if isinstance(source_contract_lanes, Mapping) else {}
    source_contract_blockers = tuple(
        dict.fromkeys(
            str(blocker)
            for lane_name in ("price_up_calibration", "after_cost_calibration")
            for blocker in (
                (source_contract_lanes.get(lane_name) or {}).get("blockers", [])
                if isinstance(source_contract_lanes.get(lane_name), Mapping)
                else []
            )
            if str(blocker).strip()
        )
    )
    source_contract_status = str(source_contract.get("status") or "unknown")
    active_performance = payload.get("active_model_performance")
    if not isinstance(active_performance, Mapping):
        active_performance = (
            dependencies.get("model_performance", {})
            if isinstance(dependencies, Mapping) and isinstance(dependencies.get("model_performance"), Mapping)
            else {}
        )
    active_performance_status = str(active_performance.get("status") or "pending")
    active_performance_reason = str(active_performance.get("reason") or "")
    training_rows = _int(payload.get("training_row_count", 0))
    calibration_rows = _int(payload.get("calibration_sample_count", 0))
    old_brier = receipt.get("old_brier_bp")
    new_brier = receipt.get("new_brier_bp")
    improvement = receipt.get("brier_improvement_bp")
    gap = receipt.get("calibration_gap_bp", payload.get("calibration_gap_bp"))
    pointer_version = receipt.get("pointer_version", payload.get("pointer_version", "n/a"))
    active_pointer = payload.get("active_pointer")
    active_pointer = active_pointer if isinstance(active_pointer, Mapping) else {}
    current_version = str(
        active_pointer.get("candidate_id")
        or active_performance.get("active_candidate_id")
        or (
            receipt.get("candidate_id")
            or payload.get("candidate_id")
            if "active_pointer" not in payload
            else "rule-only/current"
        )
        or "rule-only/current"
    )
    next_step = str(payload.get("next_step") or _learning_next_step(decision, reason))
    if active_performance_status in {"failed", "drifted"}:
        next_step = "active champion 已觸發 fault／drift；沿既有 authority rollback，修復後以新日重試。"
    summary = (
        f"status={raw_status}；matured_samples={matured}；"
        f"training_rows={training_rows}；calibration_rows={calibration_rows}；"
        f"old_brier={_display_value(old_brier)} → new_brier={_display_value(new_brier)} "
        f"(improvement={_display_value(improvement)})；"
        f"calibration_gap={_display_value(gap)}；decision={decision}；"
        f"reason={reason}；current_version={current_version}；"
        f"pointer_version={pointer_version}；active_matured_samples={active_matured} "
        f"({active_matured_dates} dates)；active_performance={active_performance_status} "
        f"({active_performance_reason or 'n/a'})；source_contract={source_contract_status} "
        f"({';'.join(source_contract_blockers) or 'n/a'})；next_step={next_step}"
    )
    if (
        raw_status in {"failed", "failed_dependency", "error"}
        or decision == "rollback"
        or active_performance_status in {"failed", "drifted"}
    ):
        display_status = "degraded"
    elif raw_status in {"skipped_no_data", "skipped_insufficient_evidence", "missing"}:
        display_status = "missing"
    elif decision == "adopt":
        display_status = "candidate"
    elif matured < 20 or "natural" in reason or "matured" in reason:
        display_status = "waiting_for_time"
    else:
        display_status = "observed"
    diagnostics = _dedupe(
        [
            reason,
            str(payload.get("data_dependency_status") or ""),
            str(payload.get("outcome_dependency_status") or ""),
            str(payload.get("drift_status") or ""),
            active_performance_status,
            active_performance_reason,
            f"source_contract:{source_contract_status}",
            *source_contract_blockers,
            str(active_evidence.get("reason") or ""),
            *(str(item) for item in payload.get("warnings", ()) or ()),
        ]
    )
    return {
        "status": display_status,
        "summary": summary,
        "diagnostics": tuple(item for item in diagnostics if item),
        "next_step": next_step,
        "source_contract_status": source_contract_status,
        "source_contract_blockers": source_contract_blockers,
    }


def _recommendation_learning_feed_item(payload: Mapping[str, Any]) -> WorkbenchEvidenceFeedItem:
    status = _recommendation_learning_payload(payload)
    return WorkbenchEvidenceFeedItem(
        item_id="recommendation_learning",
        label="Daily recommendation learning / controlled adjustment",
        status=status["status"],
        summary=status["summary"],
        source_trace="DailyRecommendationLearningRunner.latest_status",
        degraded_reason=status["diagnostics"][0] if status["diagnostics"] else "none",
        drilldown_target="evidence_review",
        diagnostics=status["diagnostics"],
    )


def _display_value(value: Any) -> str:
    return "n/a" if value is None or value == "" else str(value)


def _learning_next_step(decision: str, reason: str) -> str:
    if decision == "adopt":
        return "持續收集自然 forward capture，確認 active pointer 與 consumer 可重載。"
    if decision == "rollback":
        return "檢查資料／drift fault 與 last-good pointer，修復後以新日重試。"
    if "natural" in reason or "matured" in reason or "no_data" in reason:
        return "等待新的成熟自然 forward outcomes，未達門檻前保留 current/rule-only。"
    return "保留 current，下一個排程日重新檢查同樣本、同成本與自然成熟度。"


def _find_status(readiness_report: PreV2ReadinessReport, item_id: str) -> str:
    for item in readiness_report.items:
        if item.item_id == item_id:
            return item.status
    return "missing"


def _find_readiness_item(readiness_report: PreV2ReadinessReport, item_id: str) -> PreV2ReadinessItem | None:
    for item in readiness_report.items:
        if item.item_id == item_id:
            return item
    return None


def _find_checklist_item(items: tuple[WorkbenchChecklistItem, ...], item_id: str) -> WorkbenchChecklistItem | None:
    for item in items:
        if item.item_id == item_id:
            return item
    return None


def _operating_loop_readiness_summary(item: PreV2ReadinessItem | None) -> str:
    if item is None:
        return "readiness item 缺漏；Workbench 不補值、不讀 DB。"
    return (
        f"{_readiness_summary(item.observed_count, item.required_count)}"
        "；必須靠真實時間累積，不能用 fixture、manual edit 或 replay 補齊。"
    )


def _scheduled_status_label(status: ScheduledEvidenceStatus) -> str:
    classification = status.machine_status_classification
    if classification == MACHINE_STATUS_STALE:
        return MACHINE_STATUS_STALE
    if classification == MACHINE_STATUS_UNKNOWN:
        return MACHINE_STATUS_UNKNOWN
    # The service marks a partial initial read with ``load_checked_at`` while
    # keeping ``load_state=unknown``.  Do not let old raw ``passed`` values
    # make that untrusted read appear green.  DTO fixtures without loader
    # metadata retain their legacy projection for compatibility.
    if status.load_state == MACHINE_STATUS_UNKNOWN and status.load_checked_at is not None:
        return classification
    # Older injected DTO fixtures predate loader metadata.  Preserve their
    # established pass/degraded projection while real service reads (which
    # set load_state=current) use the source classification below.
    if status.load_state == "current" and classification in {
        MACHINE_STATUS_INVALID_EVIDENCE,
        MACHINE_STATUS_SOURCE_MISSING,
        MACHINE_STATUS_WAITING_FOR_TIME,
        MACHINE_STATUS_MACHINE_CANDIDATE,
        MACHINE_STATUS_MACHINE_DEGRADED,
    }:
        return classification
    if status.has_production_write_risk:
        return "blocked"
    if status.recommendation_status == "passed" and status.evidence_status == "passed":
        return "passed"
    if "missing" in {status.recommendation_status, status.evidence_status}:
        return "missing"
    if "failed" in {status.recommendation_status, status.evidence_status}:
        return "warning"
    return "degraded"


def _scheduled_status_summary(status: ScheduledEvidenceStatus) -> str:
    result_id = status.recommendation_result_id or "尚未保存"
    rec_count = status.recommendations_count if status.recommendations_count is not None else "未知"
    recommendation_source = status.recommendation_source
    if status.recommendation_status == "manual_observed":
        recommendation_source = "manual_result（scheduled latest_status missing）"
    return (
        f"recommendation={status.recommendation_status} / evidence={status.evidence_status}；"
        f"forward_outcomes={status.forward_outcome_status}；"
        f"source={recommendation_source}；result_id={result_id}；推薦 {rec_count} 筆；"
        f"machine_classification={status.machine_status_classification}；"
        f"load_state={status.load_state}；"
        f"last_good_loaded_at={status.last_good_loaded_at or '未知'}；"
        f"共同觀測 {status.scheduled_joint_observed_days} 天"
        f"（recommendation {status.recommendation_snapshot_observed_days} 天 / "
        f"manual recommendation {status.manual_recommendation_observed_days} 天 / "
        f"evidence dry-run {status.evidence_dry_run_observed_days} 天）。"
    )


def _readiness_summary(observed_count: int | None, required_count: int | None) -> str:
    if observed_count is None and required_count is None:
        return "readiness item available."
    if required_count is None:
        return f"已觀測 {observed_count or 0} 筆。"
    return f"{observed_count or 0}/{required_count} records observed."


def _readiness_status_classification(item: PreV2ReadinessItem) -> str:
    return classify_machine_status(
        item.status,
        (*item.blocking_reasons, *item.diagnostics, *item.next_actions),
    )


def _source_diagnostic_review_item(
    source_diagnostics: tuple[str, ...],
) -> WorkbenchReviewItem | None:
    """把 Workbench source adapter 的明示缺口投影成可操作的人工提示。

    Pre-V2 readiness 的機器缺口仍由 action/evidence feed 呈現，不能因為
    UI 想集中顯示就冒充人工審查。這裡只接收 source service 明示的
    ``decision_desk_snapshot*`` 診斷，避免把一般機器狀態重新分類。
    """
    diagnostics = tuple(str(item) for item in source_diagnostics if str(item).strip())
    if not any(item.startswith("decision_desk_snapshot") for item in diagnostics):
        return None

    if any("future_date" in item for item in diagnostics):
        summary = (
            "指定日期超過目前可用的台灣市場資料範圍；畫面已限制在可用日期，"
            "這筆未來快照不能當作今日研究依據。請查看資料來源與日期診斷。"
        )
    elif any("table_missing" in item or "db_missing" in item for item in diagnostics):
        summary = (
            "決策快照來源尚未提供或不可讀；目前只能看見降級狀態，"
            "不能把空白當成沒有風險。請查看資料來源與日期診斷。"
        )
    elif any("degraded" in item or "unavailable" in item for item in diagnostics):
        summary = (
            "決策快照讀取時發生來源錯誤；目前內容不足以支持完整研究。"
            "請查看資料來源與日期診斷後再重試。"
        )
    else:
        summary = (
            "決策快照來源有缺口；目前內容不足以支持完整研究。"
            "請查看資料來源與日期診斷。"
        )
    return WorkbenchReviewItem(
        item_id="readiness_source_gaps",
        title="決策來源缺口",
        severity="warning",
        source="workbench_source",
        summary=summary,
        drilldown_target="evidence_mode",
        code="; ".join(diagnostics[:3]),
    )


def _readiness_report_classification(readiness_report: PreV2ReadinessReport) -> str:
    classifications = tuple(
        _readiness_status_classification(item) for item in readiness_report.items
    )
    if MACHINE_STATUS_HUMAN_REVIEW in classifications:
        return MACHINE_STATUS_HUMAN_REVIEW
    for classification in (
        MACHINE_STATUS_INVALID_EVIDENCE,
        MACHINE_STATUS_SOURCE_MISSING,
        MACHINE_STATUS_WAITING_FOR_TIME,
        MACHINE_STATUS_MACHINE_CANDIDATE,
        MACHINE_STATUS_MACHINE_DEGRADED,
        MACHINE_STATUS_UNKNOWN,
    ):
        if classification in classifications:
            return classification
    return classify_machine_status(readiness_report.overall_status)


def _action_requires_human_review(item: WorkbenchActionItem) -> bool:
    return item.status_classification == MACHINE_STATUS_HUMAN_REVIEW


def _evidence_gate_status_summary(readiness_report: PreV2ReadinessReport) -> str:
    weekly = _find_readiness_item(readiness_report, "weekly_history")
    weekly_text = (
        _readiness_summary(weekly.observed_count, weekly.required_count)
        if weekly is not None
        else "weekly history readiness item missing"
    )
    if readiness_report.formal_credit_authorized:
        credit_text = "formal_credit_authorized=true"
    else:
        credit_text = (
            "formal_credit_authorized=false；目前只代表 read-only readiness，"
            "不授予 Formal evidence credit 或 production scheduler"
        )
    pending_text = _pending_weekly_review_summary(weekly)
    return f"{weekly_text}{pending_text}；{credit_text}。"


def _pending_weekly_review_summary(weekly: PreV2ReadinessItem | None) -> str:
    """Expose pending weekly periods without implying approval or Gate credit."""

    if weekly is None:
        return ""
    pending = weekly.evidence.get("pending_collection_periods")
    if not isinstance(pending, list):
        return ""
    period_labels: list[str] = []
    for item in pending:
        if not isinstance(item, Mapping):
            continue
        start = str(item.get("period_start") or "").strip()
        end = str(item.get("period_end") or "").strip()
        if start and end:
            period_labels.append(f"{start}→{end}")
    if not period_labels:
        return ""
    preview = ", ".join(period_labels[:3])
    if len(period_labels) > 3:
        preview += ", …"
    return f"；pending_human_review {len(period_labels)} 期（{preview}）"


def _status_to_severity(status: str) -> str:
    if status == STATUS_ACTION_REQUIRED:
        return "warning"
    if status == STATUS_WAITING_FOR_TIME:
        return "info"
    return _severity(status)


def _action_sort_rank(severity: str, queue_group: str, source_type: str, sequence: int) -> int:
    severity_order = {
        "critical": 0,
        "warning": 1,
        "degraded": 2,
        "missing": 3,
        "blocked": 4,
        "info": 5,
        "waiting_for_time": 6,
        "observed": 7,
        "ready": 8,
    }
    group_order = {
        "portfolio_review": 0,
        "daily_review": 1,
        "evidence_gate": 2,
        "replay_diagnostics": 3,
        "manual_review": 9,
    }
    source_order = {
        "portfolio_alert": 0,
        "risk_prompt": 1,
        "watchlist_trigger": 2,
        "pre_v2_readiness": 3,
        "replay_summary": 4,
    }
    return (
        severity_order.get(severity, 9) * 1000
        + group_order.get(queue_group, 9) * 100
        + source_order.get(source_type, 9) * 10
        + sequence
    )


def _severity(value: str) -> str:
    if value in {"critical", "warning", "info", "blocked", "ready", "observed", "degraded", "missing"}:
        return value
    return "info"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
