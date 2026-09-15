"""唯讀的每日投資決策旅程 read model。

本模組只讀取既有的 DecisionDesk snapshot、排程輸出、EvidenceEvent／Outcome
與隔離 learning receipt。它不執行推薦、forward outcome 計算、策略或任何
資料庫／持倉寫入；Workbench 只消費這個模組投影出的純 DTO。
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from app_module.decision_desk_dtos import DecisionDeskSnapshot
from app_module.evidence_event_dtos import EvidenceEvent, EvidenceOutcome
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus
from app_module.workbench_dtos import (
    WorkbenchDailyEvidence,
    WorkbenchEvidenceWindow,
    WorkbenchJourneyStep,
    WorkbenchLearningReceipt,
)


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


class DailyInvestmentJourneyService:
    """Build the Workbench's content-first daily read model without writes."""

    def __init__(self, config: Any, *, evidence_db_path: str | Path | None = None) -> None:
        self.config = config
        self.output_root = Path(config.output_root).resolve()
        self.evidence_db_path = (
            Path(evidence_db_path).resolve()
            if evidence_db_path is not None
            else Path(config.db_file).resolve()
        )

    def build(
        self,
        *,
        decision_snapshot: DecisionDeskSnapshot | None,
        scheduled_status: ScheduledEvidenceStatus,
        recommendation_learning_status: Mapping[str, Any] | None,
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
        if learning is not None and learning.active_pointer_status == "rule_only":
            warnings.append("目前 active pointer 為 rule_only；沒有 active model，不可稱為 current champion")
        if learning is not None and learning.natural_matured_sample_count == 0:
            warnings.append("隔離 learning receipt 尚無 natural matured sample；不與正式 evidence outcome 混算")

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
            journey_steps=journey_steps,
            warnings=tuple(dict.fromkeys(warnings)),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
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
        recommendations_raw: Any = payload.get("recommendations")
        run_payload: Mapping[str, Any] | None = None
        if result_id:
            runs_dir_raw = _text(payload.get("runs_dir"))
            runs_dir = self.output_root / "recommendation" / "runs"
            if runs_dir_raw:
                safe_runs_dir = _safe_output_path(self.output_root, Path(runs_dir_raw))
                if safe_runs_dir is None:
                    diagnostics.append("recommendation_snapshot_runs_dir_outside_output_root")
                else:
                    runs_dir = safe_runs_dir
            run_path = _safe_output_path(self.output_root, runs_dir / f"{result_id}.json")
            if run_path is None:
                diagnostics.append("recommendation_snapshot_run_path_unsafe")
            else:
                run_payload = _read_json_object(run_path, diagnostics, "recommendation_run")
                if run_payload is None and not run_path.exists():
                    diagnostics.append(f"recommendation_run_missing:{run_path}")
        if run_payload is not None:
            run_result_id = _text(run_payload.get("result_id"))
            if run_result_id and result_id and run_result_id != result_id:
                diagnostics.append(
                    f"recommendation_run_result_id_mismatch:{run_result_id}!={result_id}"
                )
                run_payload = None
            else:
                recommendations_raw = run_payload.get("recommendations")

        rows = _sequence_of_mappings(recommendations_raw)
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
            warnings.append("推薦 snapshot 宣稱有候選，但 run JSON 未提供候選列")
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

        run_context = _mapping(run_payload.get("run_context")) if run_payload else {}
        data_date = _date_key(
            (run_context.get("data_as_of_date") if run_context else None)
            or (run_context.get("as_of_date") if run_context else None)
            or (run_payload.get("data_as_of_date") if run_payload else None)
            or payload.get("data_as_of_date")
            or payload_date
        )
        identity = _candidate_identity(payload, cohort, run_payload, run_context)
        source_snapshot_id = _text(payload.get("source_snapshot_id"))
        if not source_snapshot_id and run_payload is not None:
            source_snapshot_id = _text(run_payload.get("source_snapshot_id"))
        source_snapshot_id = source_snapshot_id or _text(cohort.get("universe_snapshot_id"))
        source_id = _text(payload.get("source_id")) or result_id
        trace = [
            f"recommendation_snapshot.result_id={result_id or 'unknown'}",
            f"recommendation_snapshot.decision_date={payload_date or 'unknown'}",
            f"recommendation_snapshot.status={_text(payload.get('status')) or 'unknown'}",
        ]
        if cohort.get("cohort_hash"):
            trace.append(f"recommendation_snapshot.cohort_hash={_text(cohort.get('cohort_hash'))}")
        if run_payload is not None:
            trace.append(f"recommendation_run.result_id={_text(run_payload.get('result_id')) or 'unknown'}")
        for row in rows[:20]:
            code = _text(row.get("stock_code")) or _text(row.get("證券代號")) or "unknown"
            for key in ("ranking_method", "calibrated_probability_status"):
                value = _text(row.get(key))
                if value:
                    trace.append(f"recommendation_candidate[{code}].{key}={value}")
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
            f"持倉：警示 {portfolio.alert_count if portfolio.alert_count is not None else '未知'} 檔"
            f"（{portfolio_codes}）｜層級 {portfolio.alert_level or '未知'}｜品質 {_quality_label(portfolio.quality)}"
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
                f"既有持倉警示 {decision_snapshot.portfolio_alerts.alert_count if decision_snapshot.portfolio_alerts.alert_count is not None else '未知'} 檔；依既有 alert 人工覆盤。",
                "DecisionDeskSnapshot.portfolio_alerts",
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
    if portfolio_alert_count is None:
        portfolio_text = "持倉警示未知，需複核"
    elif portfolio_alert_count > 0:
        portfolio_text = f"持倉有 {portfolio_alert_count} 檔警示，需複核"
    else:
        portfolio_text = "持倉來源未見警示，仍需複核"
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
        f"盤勢：{regime}；今日研究候選：{candidate_text}；{portfolio_text}。"
        f"{evidence_surface}；{learning_surface}。"
    )


def _industry_rotation_summary(rotation: Any) -> str:
    """以來源可證明的語意呈現產業輪動，避免把代理指數冒充產業本身。"""

    quality = _quality_label(getattr(rotation, "quality", None))
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
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.execute("PRAGMA query_only = ON")
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
                (table,),
            ).fetchone()
            if row is None:
                diagnostics.append(f"evidence_table_missing:{table}")
            return row is not None
    except (OSError, sqlite3.Error) as exc:
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
