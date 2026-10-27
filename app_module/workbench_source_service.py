from __future__ import annotations

from datetime import date, datetime
from dataclasses import replace
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import json
import os
import re
import sqlite3
import time
from typing import Any, Callable

from app_module.decision_desk_dtos import DecisionDeskSnapshot, DecisionDeskQuality, RecommendationDeskSummary
from app_module.decision_capture_status_reader import read_decision_capture_status
from app_module.decision_desk_snapshot_storage_dtos import StoredDecisionDeskSnapshot
from app_module.pre_v2_readiness_service import (
    DEFAULT_MIN_DRY_RUN_DAYS,
    DEFAULT_MIN_WEEKLY_HISTORY_RECORDS,
    PreV2ReadinessService,
)
from app_module.workbench_dtos import (
    ManualSavedResearchLaneDTO,
    WorkbenchDashboardDTO,
    WorkbenchLatestCaptureStatus,
    WorkbenchPaperAccountContextDTO,
    WorkbenchPaperAccountPosition,
)
from app_module.advice_composer import AdviceComposer
from app_module.advice_dtos import AdviceDashboardDTO, AdviceMode, AdvicePolicyConfig
from app_module.advice_policy import AdvicePolicy
from app_module.personal_journal_paths import PersonalJournalPaths
from app_module.continuity_review_projection import (
    ContinuityReviewProjectionService,
)
from app_module.daily_investment_journey import DailyInvestmentJourneyService
from app_module.workbench_read_only_composer import WorkbenchReadOnlyComposer
from app_module.recommendation_learning_paths import (
    RecommendationLearningPathError,
    resolve_recommendation_learning_paths,
)
from app_module.workbench_replay_summary import load_historical_replay_summary
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjectionService,
)
from app_module.recommendation.queries import RecommendationExecutionReadSnapshot
from app_module.recommendation.contracts import (
    EXECUTION_SCHEMA_REVISION,
    ExecutionStatus,
    RecommendationExecution,
    SnapshotCohort,
    schema_version as RECOMMENDATION_EXECUTION_SCHEMA_VERSION,
)
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    execution_result_config,
)
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatusService
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.position_health_transition_read_service import (
    PositionHealthTransitionReadService,
)
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    check_read_cancelled,
    cooperative_read_cancellation,
    connect_read_only_sqlite,
)


_CAPTURE_STATUS_SCHEMA = "decision-evidence-capture.v1"
_CAPTURE_STATUS_TASK = "baldr-decision-evidence-capture-daily"
_CAPTURE_STATUS_MAX_BYTES = 1024 * 1024
_CAPTURE_RUN_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}\Z", re.ASCII)
_MARKET_DATE_QUERY_MAX_SECONDS = 2.0


class _WorkbenchRecommendationReadSession:
    """限定單次 inspect 共用讀取；新 inspect 會建立新的 session。"""

    def __init__(self, queries: Any) -> None:
        self._queries = queries
        self._snapshot: RecommendationExecutionReadSnapshot | None = None

    def list(self) -> tuple[Any, ...]:
        check_read_cancelled()
        if self._snapshot is None:
            self._snapshot = RecommendationExecutionReadSnapshot.capture(self._queries)
        check_read_cancelled()
        return self._snapshot.require_read_models()

    def __getattr__(self, name: str) -> Any:
        # legacy collision 的 get/get_legacy_original_payload 仍逐次走原始精確讀取。
        return getattr(self._queries, name)


class WorkbenchSourceService:
    """Read-only source adapter for the V2.0 Workbench prototype."""

    def __init__(
        self,
        config: Any,
        *,
        evidence_db_path: str | Path | None = None,
        research_db_path: str | Path | None = None,
        learning_evidence_projection_service: RecommendationLearningEvidenceProjectionService | None = None,
        position_health_read_service: PositionHealthTransitionReadService | None = None,
        continuity_review_projection_service: ContinuityReviewProjectionService | None = None,
        recommendation_queries: Any | None = None,
        journal_paths: PersonalJournalPaths | None = None,
        legacy_journal_read_only: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if journal_paths is None and (
            getattr(config, "personal_journal_root", None) is not None
            or getattr(config, "personal_journal_mode", None) is not None
        ):
            raise ValueError("personal_journal_selector_required")
        if journal_paths is not None and continuity_review_projection_service is not None:
            raise ValueError("personal_journal_selector_conflict")
        if legacy_journal_read_only and journal_paths is None:
            raise ValueError("personal_journal_paths_required")
        selected_continuity = (
            ContinuityReviewProjectionService.from_personal_paths(
                journal_paths, legacy_read_only=legacy_journal_read_only,
            ) if journal_paths is not None else None
        )
        self.config = config
        self._selected_paper_account_comparison: Any | None = None
        self._clock = clock or (lambda: datetime.now(TAIWAN_MARKET_TIMEZONE))
        self.recommendation_queries = (
            recommendation_queries
            if recommendation_queries is not None
            else build_recommendation_execution_queries(config)
        )
        self.evidence_db_path = Path(evidence_db_path) if evidence_db_path is not None else Path(config.db_file)
        self.research_db_path = (
            Path(research_db_path) if research_db_path is not None else Path(config.research_run_db_file)
        )
        self.readiness_service = PreV2ReadinessService(
            config,
            evidence_db_path=self.evidence_db_path,
            research_db_path=self.research_db_path,
            approved_weekly_history_projection_path=os.environ.get("WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH"),
            recommendation_queries=self.recommendation_queries,
        )
        self.composer = WorkbenchReadOnlyComposer(clock=self._clock)
        self.scheduled_status_service = ScheduledEvidenceStatusService(
            config,
            recommendation_queries=self.recommendation_queries,
        )
        self.learning_evidence_projection_service = (
            learning_evidence_projection_service
            or RecommendationLearningEvidenceProjectionService(config)
        )
        self.daily_investment_journey_service = DailyInvestmentJourneyService(
            config,
            evidence_db_path=self.evidence_db_path,
        )
        self.position_health_read_service = (
            position_health_read_service
            or PositionHealthTransitionReadService(
                Path(config.output_root) / "position_health_transition"
            )
        )
        # This is deliberately a direct read adapter.  Do not construct
        # JournalService/PortfolioJsonlStore here: their constructors can
        # create output directories on an otherwise read-only Workbench load.
        self.continuity_review_projection_service = (
            continuity_review_projection_service
            or selected_continuity
            or ContinuityReviewProjectionService.from_output_root(config.output_root)
        )

    def select_paper_account_context(self, comparison: Any) -> None:
        """保留 UI 明確選取的 exact Paper 比較；僅供 Workbench 背景呈現。"""
        from app_module.portfolio_research_scenario_service import (
            PortfolioResearchScenarioComparison,
        )

        if not isinstance(comparison, PortfolioResearchScenarioComparison):
            raise ValueError("typed_portfolio_research_comparison_required")
        if comparison.account.account_kind != "paper":
            raise ValueError("paper_account_context_required")
        if (
            comparison.request.account_kind != "paper"
            or comparison.request.portfolio_id != comparison.account.portfolio_id
            or comparison.request.snapshot_id != comparison.account.snapshot_id
        ):
            raise ValueError("paper_account_identity_mismatch")
        self._selected_paper_account_comparison = comparison

    def inspect(
        self,
        *,
        decision_date: str | None = None,
        multi_day_record_path: str | Path | None = None,
        min_weekly_records: int = DEFAULT_MIN_WEEKLY_HISTORY_RECORDS,
        min_dry_run_days: int = DEFAULT_MIN_DRY_RUN_DAYS,
        agent_report_limit: int = 5,
        replay_summary_json: str | Path | None = None,
        recommendation_learning_status_json: str | Path | None = None,
        continuity_as_of: datetime | str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> WorkbenchDashboardDTO:
        with cooperative_read_cancellation(cancel_callback):
            check_read_cancelled()
            return self._inspect(
                decision_date=decision_date,
                multi_day_record_path=multi_day_record_path,
                min_weekly_records=min_weekly_records,
                min_dry_run_days=min_dry_run_days,
                agent_report_limit=agent_report_limit,
                replay_summary_json=replay_summary_json,
                recommendation_learning_status_json=recommendation_learning_status_json,
                continuity_as_of=continuity_as_of,
            )

    def _inspect(
        self,
        *,
        decision_date: str | None = None,
        multi_day_record_path: str | Path | None = None,
        min_weekly_records: int = DEFAULT_MIN_WEEKLY_HISTORY_RECORDS,
        min_dry_run_days: int = DEFAULT_MIN_DRY_RUN_DAYS,
        agent_report_limit: int = 5,
        replay_summary_json: str | Path | None = None,
        recommendation_learning_status_json: str | Path | None = None,
        continuity_as_of: datetime | str | None = None,
    ) -> WorkbenchDashboardDTO:
        observed_at = self._clock()
        evaluation_at = _as_taipei_datetime(observed_at)
        evaluation_date = evaluation_at.date()
        recommendation_read_session = _WorkbenchRecommendationReadSession(
            self.recommendation_queries
        )
        decision_snapshot, source_diagnostics = self._load_decision_snapshot(
            decision_date,
            today=evaluation_date,
        )
        market_data_as_of_date, market_index_as_of_date = self._load_market_data_as_of_dates(
            evaluation_date
        )
        latest_capture_status = self._load_latest_capture_status(evaluation_date, observed_at=observed_at)
        check_read_cancelled()
        readiness_report = self.readiness_service.inspect(
            decision_date=decision_date,
            multi_day_record_path=multi_day_record_path,
            min_weekly_records=min_weekly_records,
            min_dry_run_days=min_dry_run_days,
            agent_report_limit=agent_report_limit,
            recommendation_queries=recommendation_read_session,
        )
        check_read_cancelled()
        agent_report_sample = self.readiness_service.build_agent_report_sample(
            limit=agent_report_limit
        )
        check_read_cancelled()
        historical_replay_summary = (
            load_historical_replay_summary(replay_summary_json) if replay_summary_json is not None else None
        )
        check_read_cancelled()
        scheduled_status = self.scheduled_status_service.load_latest(
            recommendation_queries=recommendation_read_session,
        )
        check_read_cancelled()
        recommendation_learning_status, learning_diagnostics = self._load_recommendation_learning_status(
            recommendation_learning_status_json
        )
        check_read_cancelled()
        source_diagnostics.extend(learning_diagnostics)
        continuity_reviews = self.continuity_review_projection_service.project(
            as_of=continuity_as_of,
        )
        check_read_cancelled()
        source_mode = "read_only_sources_plus_historical_replay" if historical_replay_summary else "read_only_sources"
        dashboard = self.composer.compose(
            decision_snapshot=decision_snapshot,
            readiness_report=readiness_report,
            agent_report_sample=agent_report_sample,
            scheduled_status=scheduled_status,
            historical_replay_summary=historical_replay_summary,
            source_mode=source_mode,
            source_diagnostics=tuple(source_diagnostics),
            recommendation_learning_status=recommendation_learning_status,
            continuity_reviews=continuity_reviews,
            evaluation_at=evaluation_at,
            market_data_as_of_date=market_data_as_of_date,
            market_index_as_of_date=market_index_as_of_date,
            latest_capture_status=latest_capture_status,
        )
        learning_projection = self.learning_evidence_projection_service.inspect(
            requested_date=dashboard.as_of_date.isoformat()
        )
        check_read_cancelled()
        daily_evidence, recommendation_read_model = (
            self.daily_investment_journey_service.build_with_recommendation_read(
                decision_snapshot=decision_snapshot,
                scheduled_status=scheduled_status,
                recommendation_learning_status=recommendation_learning_status,
                recommendation_learning_projection=learning_projection,
                requested_decision_date=dashboard.as_of_date.isoformat(),
            )
        )
        check_read_cancelled()
        advice_dashboard = self._compose_scheduled_candidate_advice(
            recommendation_read_model,
            daily_evidence=daily_evidence,
            decision_date=dashboard.as_of_date.isoformat(),
        )
        advice_dashboard = self._bind_advice_source_identity(
            advice_dashboard,
            recommendation_read_model,
            daily_evidence=daily_evidence,
        )
        position_health = self.position_health_read_service.read_latest(
            expected_decision_date=dashboard.as_of_date.isoformat(),
        )
        check_read_cancelled()
        return replace(
            dashboard,
            advice_dashboard=advice_dashboard,
            daily_evidence=daily_evidence,
            position_health=position_health,
            paper_account_context=self._paper_account_context(
                dashboard.as_of_date,
                evaluation_at,
            ),
        )

    def load_manual_saved_research(self, result_id: str) -> ManualSavedResearchLaneDTO:
        """唯讀載入使用者明選的 canonical 結果，組成獨立 research-only lane。"""

        if type(result_id) is not str or not result_id or result_id.strip() != result_id:
            raise ValueError("manual_saved_research_result_id_invalid")
        read_model = self.recommendation_queries.get(result_id)
        if read_model is None:
            raise ValueError("manual_saved_research_result_missing")
        if (
            getattr(read_model, "result_id", None) != result_id
            or getattr(read_model, "integrity_basis", None)
            != "canonical_payload_and_index_verified"
            or getattr(read_model, "legacy_result", None) is not None
            or getattr(read_model, "execution", None) is None
        ):
            raise ValueError("manual_saved_research_result_not_canonical")
        execution = read_model.execution
        if (
            type(execution) is not RecommendationExecution
            or execution.result_id != result_id
            or execution.status is not ExecutionStatus.COMPLETED
            or not execution.items
            or read_model.schema_version != RECOMMENDATION_EXECUTION_SCHEMA_VERSION
            or read_model.schema_revision != EXECUTION_SCHEMA_REVISION
            or execution.schema_version != RECOMMENDATION_EXECUTION_SCHEMA_VERSION
            or execution.schema_revision != EXECUTION_SCHEMA_REVISION
            or type(read_model.payload_hash) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", read_model.payload_hash) is None
        ):
            raise ValueError("manual_saved_research_result_identity_or_schema_invalid")

        config = execution_result_config(execution)
        decision_date_text = config.get("decision_date")
        data_as_of_date_text = (
            config.get("data_as_of_date")
            or config.get("data_date")
        )
        context_date = execution.context.as_of_date
        request_date = execution.request.as_of_date
        if (
            context_date is None
            or request_date is None
            or context_date != request_date
        ):
            raise ValueError("manual_saved_research_result_dates_missing_or_mismatched")
        if type(decision_date_text) is not str or not decision_date_text:
            decision_date_text = context_date.isoformat()
        if type(data_as_of_date_text) is not str or not data_as_of_date_text:
            data_as_of_date_text = context_date.isoformat()
        try:
            decision_date = date.fromisoformat(decision_date_text)
            data_as_of_date = date.fromisoformat(data_as_of_date_text)
        except ValueError as exc:
            raise ValueError("manual_saved_research_result_dates_invalid") from exc
        if (
            decision_date.isoformat() != decision_date_text
            or data_as_of_date.isoformat() != data_as_of_date_text
            or data_as_of_date > decision_date
        ):
            raise ValueError("manual_saved_research_result_dates_invalid")

        quality_status = execution.quality.status.value
        evidence_quality = {
            "complete": "OBSERVED",
            "degraded": "DEGRADED",
        }.get(quality_status, "UNKNOWN")
        warnings = (
            "這是你明確選取的保存結果，日期沿用原結果；不是今日排程候選。",
            "此區僅供 Professional 研究；不構成正式 Advice、來源接受、PIT 或 Gate 通過。",
            f"保存 execution 品質狀態為 {quality_status}；未由本次載入重新核驗逐來源品質或授權。",
            *tuple(execution.quality.warnings),
            *tuple(execution.context.warnings),
        )
        policy_config = AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL)
        advice = AdviceComposer(AdvicePolicy(policy_config)).compose(
            recommendations=read_model,
            portfolio_result=None,
            evidence_quality=evidence_quality,
            decision_date=decision_date,
            data_as_of_date=data_as_of_date,
            mode=AdviceMode.PROFESSIONAL,
            evidence_warnings=warnings,
            research_only=True,
        )
        return ManualSavedResearchLaneDTO(
            result_id=result_id,
            payload_sha256=read_model.payload_hash,
            decision_date=decision_date_text,
            data_as_of_date=data_as_of_date_text,
            strategy_version=(
                str(config.get("strategy_version") or "")
                or (execution.context.strategy_identity.strategy_version_id
                    if execution.context.strategy_identity is not None
                    else "")
                or ""
            ),
            advice_dashboard=advice,
        )

    def _paper_account_context(
        self, decision_date: date, evaluation_at: datetime
    ) -> WorkbenchPaperAccountContextDTO | None:
        comparison = self._selected_paper_account_comparison
        if comparison is None:
            return None
        from app_module.portfolio_research_scenario_service import (
            PortfolioResearchScenarioComparison,
        )

        if not isinstance(comparison, PortfolioResearchScenarioComparison):
            return None
        account = comparison.account
        comparison_date = comparison.decision_at.astimezone(
            TAIWAN_MARKET_TIMEZONE
        ).date()
        account_date = date.fromisoformat(account.as_of_date)
        stale_reason = ""
        if comparison_date != decision_date or account_date > decision_date:
            stale_reason = "所選 Paper snapshot 晚於 Workbench 決策日，或比較日期不符。"
        elif account.available_at > comparison.decision_at:
            stale_reason = "Paper snapshot 的可得時間晚於比較決策時鐘。"
        elif comparison.decision_at > evaluation_at:
            stale_reason = "比較決策時鐘晚於 Workbench 評估時鐘。"
        if stale_reason:
            return WorkbenchPaperAccountContextDTO(
                status="stale",
                decision_date=decision_date,
                portfolio_id=account.portfolio_id,
                snapshot_id=account.snapshot_id,
                as_of_date=account_date,
                available_at=account.available_at,
                source_hash=account.source_hash,
                diagnostic=stale_reason,
            )
        positions = tuple(
            WorkbenchPaperAccountPosition(
                stock_code=row.stock_code,
                quantity=row.quantity,
                mark_price=row.mark_price,
                market_value=row.market_value,
                weight_bp=account.current_weights.weight_for(row.stock_code),
            )
            for row in account.valuation.positions
        )
        return WorkbenchPaperAccountContextDTO(
            status="available",
            decision_date=decision_date,
            portfolio_id=account.portfolio_id,
            snapshot_id=account.snapshot_id,
            as_of_date=account_date,
            available_at=account.available_at,
            source_hash=account.source_hash,
            total_value=account.valuation.total_value,
            cash_amount=account.valuation.cash_amount,
            positions=positions,
            diagnostic=(
                "已核對明確選取的 Paper snapshot；來源日如早於決策日，僅作歷史背景。"
                "不代表 Advice 風險預算。"
            ),
        )

    @staticmethod
    def _bind_advice_source_identity(
        advice_dashboard: AdviceDashboardDTO,
        recommendation_read_model: Any | None,
        *,
        daily_evidence: Any,
    ) -> AdviceDashboardDTO:
        """只把已由每日旅程對齊的 exact read-model identity 綁到 Advice 列。"""
        if (
            recommendation_read_model is None
            or daily_evidence.candidate_status
            not in {"candidate", "candidate_degraded"}
            or not daily_evidence.candidate_result_id
            or not daily_evidence.candidate_symbols
        ):
            return advice_dashboard
        try:
            result_id = recommendation_read_model.result_id
        except (AttributeError, TypeError, ValueError):
            return advice_dashboard
        if result_id != daily_evidence.candidate_result_id:
            return advice_dashboard
        result_hash: str | None = None
        if (
            getattr(recommendation_read_model, "execution", None) is not None
            and getattr(recommendation_read_model, "integrity_basis", None)
            == "canonical_payload_and_index_verified"
        ):
            payload_hash = getattr(recommendation_read_model, "payload_hash", None)
            if isinstance(payload_hash, str) and re.fullmatch(
                r"sha256:[0-9a-f]{64}", payload_hash
            ) is not None:
                result_hash = payload_hash
        eligible_symbols = set(daily_evidence.candidate_symbols)
        bound_rows = tuple(
            replace(
                row,
                source_result_id=result_id,
                source_payload_sha256=result_hash,
            )
            if (
                row.stock_code in eligible_symbols
                and row.decision_date == daily_evidence.decision_date
                and row.data_as_of_date
                == (daily_evidence.candidate_data_date or "")
            )
            else row
            for row in advice_dashboard.recommendations
        )
        if bound_rows == advice_dashboard.recommendations:
            return advice_dashboard
        return replace(advice_dashboard, recommendations=bound_rows)

    @staticmethod
    def _compose_scheduled_candidate_advice(
        recommendation_read_model: Any | None,
        *,
        daily_evidence: Any,
        decision_date: str,
    ) -> AdviceDashboardDTO:
        """Expose only the exact, verified current scheduled read as research candidates."""

        policy_config = AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL)
        if recommendation_read_model is None or daily_evidence.candidate_status not in {
            "candidate",
            "candidate_degraded",
        }:
            status = str(daily_evidence.candidate_status or "unknown")
            if status == "candidate":
                reason = "當日候選列缺少通過身分核對的保存結果；未注入 Advice。"
                code = "verified_recommendation_read_missing"
            else:
                reason = f"當日候選狀態為「{status}」；未注入 Advice。請檢查每日來源日期、品質與保存結果身份。"
                code = f"scheduled_candidate_status:{status}"
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date=(daily_evidence.candidate_data_date or ""),
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=(code,),
                warnings=tuple(dict.fromkeys((reason, *tuple(daily_evidence.warnings)))),
            )
        candidate_result_id = getattr(daily_evidence, "candidate_result_id", None)
        try:
            saved_result_id = recommendation_read_model.result_id
        except (AttributeError, TypeError, ValueError):
            saved_result_id = None
        if (
            not isinstance(candidate_result_id, str)
            or not candidate_result_id
            or saved_result_id != candidate_result_id
        ):
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date=(daily_evidence.candidate_data_date or ""),
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=("scheduled_candidate_result_identity_mismatch",),
                warnings=(
                    "每日候選與保存推薦結果的身份無法精確核對；未注入 Advice。",
                ),
            )
        candidate_symbols = getattr(daily_evidence, "candidate_symbols", ())
        if not isinstance(candidate_symbols, (tuple, list)):
            candidate_symbols = ()
        eligible_symbols = {
            symbol.strip()
            for symbol in candidate_symbols
            if isinstance(symbol, str) and symbol.strip()
        }
        if not eligible_symbols:
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date=(daily_evidence.candidate_data_date or ""),
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=("scheduled_candidate_cohort_missing",),
                warnings=("每日候選股票清單缺失；未注入 Advice。",),
            )
        if recommendation_read_model.execution is not None:
            config = execution_result_config(recommendation_read_model.execution)
        elif recommendation_read_model.legacy_result is not None:
            config = recommendation_read_model.legacy_result.config
        else:
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date=(daily_evidence.candidate_data_date or ""),
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=("recommendation_read_model_unsupported",),
                warnings=("保存推薦格式無法由 Advice 安全讀取；未注入候選。",),
            )
        # 沒有精確綁定的採用／鎖參／揭露證據時，保留研究候選供每日判讀，
        # 並強制降為 RESEARCH；不得把保存結果中的 promoted 字樣當正式建議資格。
        promoted_without_acceptance = config.get("strategy_status") == "promoted"
        data_as_of_date = daily_evidence.candidate_data_date
        if not data_as_of_date:
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date="",
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=("candidate_data_date_missing",),
                warnings=("候選資料日期缺失；不能把決策日代作資料日，因此未注入 Advice。",),
            )
        if data_as_of_date > decision_date:
            return AdviceDashboardDTO(
                decision_date=decision_date,
                data_as_of_date=data_as_of_date,
                mode=AdviceMode.PROFESSIONAL,
                policy=policy_config,
                diagnostics=("candidate_data_date_after_decision_date",),
                warnings=("候選資料日晚於決策日；已阻擋 Advice 注入。",),
            )
        evidence_quality = (
            "OBSERVED" if daily_evidence.candidate_quality == "observed" else "DEGRADED"
        )
        warnings: tuple[str, ...] = (
            "排程候選已核對保存結果與日期／cohort；目前僅供研究，不代表策略已通過正式採用 Gate。",
            "此策略建議不需要連接真實帳戶；持倉與交易由使用者手動記錄。這裡不計算個人配置或加碼金額。",
        )
        if daily_evidence.candidate_status == "candidate_degraded":
            warnings = (
                "整體候選 cohort 有缺漏或降級股票；WorkBench 仍逐檔依同一 canonical cohort 判品質，其他股票不會自動降級此候選。",
                *warnings,
            )
        if promoted_without_acceptance:
            warnings = (
                "保存策略標示為 promoted，但沒有精確綁定的正式採用、參數鎖定與揭露核驗證據；此列已降為研究候選，不構成正式新增部位建議。",
                *warnings,
            )
        per_stock_quality = WorkbenchSourceService._candidate_quality_by_stock(
            recommendation_read_model,
            candidate_symbols=eligible_symbols,
            candidate_identity=getattr(daily_evidence, "candidate_identity", ()),
        )
        advice = AdviceComposer(AdvicePolicy(policy_config)).compose(
            recommendations=recommendation_read_model,
            portfolio_result=None,
            evidence_quality=evidence_quality,
            decision_date=decision_date,
            data_as_of_date=data_as_of_date,
            mode=AdviceMode.PROFESSIONAL,
            evidence_warnings=warnings,
            research_only=promoted_without_acceptance,
            evidence_quality_by_stock=per_stock_quality,
        )
        cohort_rows = tuple(
            row
            for row in advice.recommendations
            if row.stock_code in eligible_symbols
            or (
                not row.stock_code
                and row.source_trace == ("AdviceComposer.refusal",)
            )
        )
        excluded_row_count = len(advice.recommendations) - len(cohort_rows)
        if excluded_row_count:
            advice = replace(
                advice,
                recommendations=cohort_rows,
                diagnostics=tuple(
                    dict.fromkeys(
                        (*advice.diagnostics, "scheduled_candidate_cohort_filtered")
                    )
                ),
                warnings=tuple(
                    dict.fromkeys(
                        (
                            *advice.warnings,
                            "Advice 僅列出每日旅程核對的候選股票；保存結果內其他股票已排除。",
                        )
                    )
                ),
            )
        if promoted_without_acceptance:
            advice = replace(
                advice,
                diagnostics=tuple(dict.fromkeys((
                    *advice.diagnostics,
                    "promoted_strategy_acceptance_evidence_missing_research_only",
                ))),
            )
        return advice

    @staticmethod
    def _candidate_quality_by_stock(
        read_model: Any,
        *,
        candidate_symbols: set[str],
        candidate_identity: object,
    ) -> dict[str, str]:
        """只從 exact canonical cohort 取逐股品質，不讓其他股票降級候選。"""

        if (
            getattr(read_model, "integrity_basis", None)
            != "canonical_payload_and_index_verified"
            or getattr(read_model, "legacy_result", None) is not None
        ):
            return {}
        execution = getattr(read_model, "execution", None)
        if (
            type(execution) is not RecommendationExecution
            or execution.result_id != getattr(read_model, "result_id", None)
        ):
            return {}
        cohort = execution.context.snapshot_cohort
        if type(cohort) is not SnapshotCohort:
            return {}
        if not candidate_symbols.issubset(set(cohort.eligible_symbols)):
            return {}
        identity_parts = (
            candidate_identity
            if isinstance(candidate_identity, (tuple, list))
            else ()
        )
        if f"cohort_hash={cohort.cohort_hash}" not in identity_parts:
            return {}

        quality_map: dict[str, str] = {}
        for stock_code in candidate_symbols:
            coverage = cohort.coverage_by_symbol.get(stock_code)
            if coverage is None:
                continue
            quality = (coverage.quality or "").strip().lower()
            if quality == "observed":
                quality_map[stock_code] = "OBSERVED"
            elif quality == "degraded":
                quality_map[stock_code] = "DEGRADED"
            elif quality == "missing":
                quality_map[stock_code] = "MISSING"
        return quality_map

    def _load_recommendation_learning_status(
        self,
        explicit_path: str | Path | None,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Load only the runner's immutable latest status; never execute the runner in UI."""

        if explicit_path is not None:
            path = Path(explicit_path)
        else:
            try:
                path = resolve_recommendation_learning_paths(
                    data_root=getattr(self.config, "data_root", None)
                ).latest_status_path
            except RecommendationLearningPathError as exc:
                return (
                    {
                        "status": "failed",
                        "reason": "recommendation_learning_output_root_invalid",
                        "decision": "retain_current",
                        "decision_reason": "recommendation_learning_output_root_invalid",
                        "warnings": [str(exc)],
                    },
                    ["recommendation_learning_output_root_invalid"],
                )
        if not path.is_file():
            return None, []
        check_read_cancelled()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            check_read_cancelled()
            return {
                "status": "failed",
                "reason": "recommendation_learning_latest_status_invalid",
                "decision": "retain_current",
                "decision_reason": "recommendation_learning_latest_status_invalid",
                "warnings": [f"{type(exc).__name__}"],
            }, ["recommendation_learning_latest_status_invalid"]
        check_read_cancelled()
        if not isinstance(payload, dict):
            return {
                "status": "failed",
                "reason": "recommendation_learning_latest_status_not_object",
                "decision": "retain_current",
                "decision_reason": "recommendation_learning_latest_status_not_object",
            }, ["recommendation_learning_latest_status_not_object"]
        return payload, []

    def _load_decision_snapshot(
        self,
        decision_date: str | None,
        *,
        today: date | None = None,
    ) -> tuple[DecisionDeskSnapshot | None, list[str]]:
        diagnostics: list[str] = []
        today = today or _as_taipei_datetime(self._clock()).date()
        cutoff_date, requested_future_date = _bounded_decision_date(decision_date, today)
        try:
            with closing(_connect_read_only(self.evidence_db_path)) as conn:
                if not _table_exists(conn, "decision_desk_snapshots"):
                    diagnostics.append("decision_desk_snapshots_table_missing")
                    return None, diagnostics
                future_rows = conn.execute(
                    """
                    SELECT DISTINCT decision_date
                    FROM decision_desk_snapshots
                    WHERE snapshot_status = 'active' AND decision_date > ?
                    ORDER BY decision_date ASC
                    """,
                    (today.isoformat(),),
                ).fetchall()
                future_dates = tuple(str(item["decision_date"]) for item in future_rows)
                if requested_future_date is not None:
                    diagnostics.append(
                        "decision_desk_snapshot_request_future_date:"
                        f"{requested_future_date.isoformat()}:today={today.isoformat()}"
                    )
                diagnostics.extend(
                    "decision_desk_snapshot_future_date:"
                    f"{item}:today={today.isoformat()}"
                    for item in future_dates
                )
                row = conn.execute(
                    """
                    SELECT *
                    FROM decision_desk_snapshots
                    WHERE decision_date <= ? AND snapshot_status = 'active'
                    ORDER BY decision_date DESC, created_at DESC
                    LIMIT 1
                    """,
                    (cutoff_date,),
                ).fetchone()
        except FileNotFoundError as exc:
            diagnostics.append(f"decision_desk_snapshot_db_missing:{exc}")
            return None, diagnostics
        except sqlite3.Error as exc:
            check_read_cancelled()
            diagnostics.append(f"decision_desk_snapshot_unavailable:{exc}")
            return None, diagnostics

        if row is None:
            diagnostics.append("decision_desk_snapshot_missing")
            return None, diagnostics
        try:
            stored = _row_to_stored_snapshot(dict(row))
            snapshot = stored.to_decision_desk_snapshot()
            payload = stored.metadata_json.get("loop_snapshot")
            if payload is not None:
                if not isinstance(payload, dict):
                    raise ValueError("loop_snapshot 必須為 object")
                recommendation = payload.get("recommendations")
                summary = None
                if recommendation is not None:
                    if not isinstance(recommendation, dict):
                        raise ValueError("recommendations 必須為 object")
                    recommendation_date = date.fromisoformat(recommendation["as_of_date"]) if recommendation.get("as_of_date") else None
                    if recommendation_date is not None and recommendation_date > snapshot.as_of_date:
                        raise ValueError("保存推薦日期晚於快照決策日")
                    summary = RecommendationDeskSummary(
                        as_of_date=recommendation_date, quality=DecisionDeskQuality(recommendation["quality"]),
                        warnings=tuple(recommendation.get("warnings", ())), result_id=str(recommendation.get("result_id", "")),
                        stock_codes=tuple(recommendation.get("stock_codes", ())), profile_id=str(recommendation.get("profile_id", "")),
                        context=deepcopy(recommendation.get("context", {})),
                    )
                lineage = payload.get("source_lineage", {})
                if not isinstance(lineage, dict):
                    raise ValueError("source_lineage 必須為 object")
                snapshot = replace(snapshot, recommendations=summary, source_lineage=deepcopy(lineage))
            return snapshot, diagnostics
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            diagnostics.append(f"decision_desk_snapshot_degraded:{exc}")
            return None, diagnostics

    def _load_market_data_as_of_dates(
        self,
        evaluation_date: date,
    ) -> tuple[date | None, date | None]:
        """Read maximum canonical market dates without creating or upgrading a database."""

        database_path = Path(self.config.db_file)
        if not database_path.is_file():
            return None, None
        check_read_cancelled()
        try:
            with closing(_connect_read_only(database_path)) as conn:
                stock_price_date = _latest_market_table_date(
                    conn,
                    table_name="daily_prices",
                    evaluation_date=evaluation_date,
                )
                market_index_date = _latest_market_table_date(
                    conn,
                    table_name="market_indices",
                    evaluation_date=evaluation_date,
                    index_name="TAIEX",
                )
        except (OSError, sqlite3.Error):
            check_read_cancelled()
            return None, None
        check_read_cancelled()
        return stock_price_date, market_index_date

    def _load_latest_capture_status(
        self, evaluation_date: date, *, observed_at: datetime | None = None,
    ) -> WorkbenchLatestCaptureStatus:
        """沿共同receipt reader取安全摘要；不借latest字串宣稱已保存。"""
        path = (Path(self.config.output_root) / "scheduled" /
                "decision_evidence_capture" / "latest_status.json")
        cutoff = observed_at if observed_at is not None else datetime.now(TAIWAN_MARKET_TIMEZONE)
        capture = read_decision_capture_status(path, observed_at=cutoff)
        if capture.read_state != "verified":
            return WorkbenchLatestCaptureStatus()
        decision_date = _canonical_iso_date(capture.decision_date)
        if decision_date is None or decision_date > evaluation_date:
            return WorkbenchLatestCaptureStatus()
        if capture.snapshot_status == "timeout" or capture.snapshot_execution_status == "timed_out":
            return WorkbenchLatestCaptureStatus(
                status="timeout", run_id=capture.run_id, decision_date=decision_date,
                failure_reason="snapshot_cli_timeout", snapshot_saved=capture.snapshot_saved,
            )
        if capture.snapshot_saved is True or capture.snapshot_duplicate is True:
            return WorkbenchLatestCaptureStatus(
                status="saved", run_id=capture.run_id, decision_date=decision_date,
                snapshot_saved=capture.snapshot_saved,
            )
        if capture.raw_status == "failed" and any(reason.startswith("snapshot_") for reason in capture.failure_reasons):
            return WorkbenchLatestCaptureStatus(
                status="failed", run_id=capture.run_id, decision_date=decision_date,
                failure_reason="snapshot_capture_failed", snapshot_saved=capture.snapshot_saved,
            )
        return WorkbenchLatestCaptureStatus()


def _as_taipei_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Workbench clock must return a timezone-aware datetime")
    return value.astimezone(TAIWAN_MARKET_TIMEZONE).replace(microsecond=0)


def _canonical_iso_date(raw: Any) -> date | None:
    if not isinstance(raw, str) or raw != raw.strip():
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == raw else None


def _latest_market_table_date(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    evaluation_date: date,
    index_name: str | None = None,
) -> date | None:
    if table_name not in {"daily_prices", "market_indices"}:
        return None
    if not _table_exists(conn, table_name) or not _table_has_column(conn, table_name, "日期"):
        return None

    where_parts: list[str] = []
    parameters: list[Any] = []
    if index_name is not None:
        if not _table_has_column(conn, table_name, "指數名稱"):
            return None
        where_parts.append('"指數名稱" = ?')
        parameters.append(index_name)

    candidates: list[date] = []
    deadline = time.monotonic() + _MARKET_DATE_QUERY_MAX_SECONDS

    def abort_bounded_read() -> int:
        try:
            check_read_cancelled()
        except ReadOperationCancelled:
            return 1
        return int(time.monotonic() >= deadline)

    conn.set_progress_handler(abort_bounded_read, 1000)
    try:
        for length, pattern, cutoff, compact in (
            (
                10,
                "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]",
                evaluation_date.isoformat(),
                False,
            ),
            (
                8,
                "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]",
                evaluation_date.strftime("%Y%m%d"),
                True,
            ),
        ):
            if time.monotonic() >= deadline:
                # A partial MAX over only one supported date encoding is not a
                # trustworthy latest date. Fail closed if both encodings did
                # not complete within the shared budget.
                return None
            predicates = [*where_parts, '"日期" <= ?', 'LENGTH("日期") = ?', '"日期" GLOB ?']
            query_parameters = [*parameters, cutoff, length, pattern]
            row = conn.execute(
                f'SELECT MAX("日期") AS latest_date FROM "{table_name}" '
                f'WHERE {" AND ".join(predicates)}',
                query_parameters,
            ).fetchone()
            if time.monotonic() >= deadline:
                return None
            raw_date = row["latest_date"] if row is not None else None
            parsed = _canonical_market_date(raw_date, compact=compact)
            if parsed is not None:
                candidates.append(parsed)
    except sqlite3.Error:
        return None
    finally:
        conn.set_progress_handler(None, 0)
    return max(candidates) if candidates else None


def _canonical_market_date(raw: Any, *, compact: bool) -> date | None:
    if not isinstance(raw, str) or raw != raw.strip():
        return None
    if compact:
        if len(raw) != 8 or not raw.isascii() or not raw.isdigit():
            return None
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return _canonical_iso_date(raw)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = connect_read_only_sqlite(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if table_name not in {"daily_prices", "market_indices"}:
        return False
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return any(str(row["name"]) == column_name for row in rows)


def _row_to_stored_snapshot(row: dict[str, Any]) -> StoredDecisionDeskSnapshot:
    return StoredDecisionDeskSnapshot(
        snapshot_id=str(row["snapshot_id"]),
        snapshot_hash=str(row["snapshot_hash"]),
        decision_date=str(row["decision_date"]),
        as_of_date=str(row["as_of_date"]),
        source_version=str(row["source_version"]),
        builder_version=str(row["builder_version"]),
        data_quality=str(row["data_quality"]),
        warnings_json=_json_value(row["warnings_json"], []),
        market_regime_json=_json_value(row["market_regime_json"], {}),
        market_breadth_json=_json_value(row["market_breadth_json"], {}),
        sector_rotation_json=_json_value(row["sector_rotation_json"], {}),
        relative_strength_liquidity_json=_json_value(row["relative_strength_liquidity_json"], {}),
        watchlist_trigger_json=_json_value(row["watchlist_trigger_json"], {}),
        portfolio_alert_json=_json_value(row["portfolio_alert_json"], {}),
        risk_prompt_json=_json_value(row["risk_prompt_json"], {}),
        fundamental_diagnostics_json=_json_value(row["fundamental_diagnostics_json"], {}),
        metadata_json=_json_value(row["metadata_json"], {}),
        snapshot_status=str(row["snapshot_status"]),
        created_at=str(row["created_at"]),
    )


def _json_value(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    return json.loads(str(raw))


def _bounded_decision_date(
    decision_date: str | None,
    today: date,
) -> tuple[str, date | None]:
    """把 Workbench 的 current 查詢上限限制在台灣市場今天。"""

    if not decision_date:
        return today.isoformat(), None
    text = str(decision_date).strip()[:10]
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text, None
    if parsed > today:
        return today.isoformat(), parsed
    return parsed.isoformat(), None
