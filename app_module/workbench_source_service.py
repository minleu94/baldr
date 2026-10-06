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
from app_module.decision_desk_snapshot_storage_dtos import StoredDecisionDeskSnapshot
from app_module.pre_v2_readiness_service import (
    DEFAULT_MIN_DRY_RUN_DAYS,
    DEFAULT_MIN_WEEKLY_HISTORY_RECORDS,
    PreV2ReadinessService,
)
from app_module.workbench_dtos import (
    WorkbenchDashboardDTO,
    WorkbenchLatestCaptureStatus,
)
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
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
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
        evaluation_at = _as_taipei_datetime(self._clock())
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
        latest_capture_status = self._load_latest_capture_status(evaluation_date)
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
        daily_evidence = self.daily_investment_journey_service.build(
            decision_snapshot=decision_snapshot,
            scheduled_status=scheduled_status,
            recommendation_learning_status=recommendation_learning_status,
            recommendation_learning_projection=learning_projection,
            requested_decision_date=dashboard.as_of_date.isoformat(),
        )
        check_read_cancelled()
        position_health = self.position_health_read_service.read_latest(
            expected_decision_date=dashboard.as_of_date.isoformat(),
        )
        check_read_cancelled()
        return replace(
            dashboard,
            daily_evidence=daily_evidence,
            position_health=position_health,
        )

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
        self,
        evaluation_date: date,
    ) -> WorkbenchLatestCaptureStatus:
        """Read a bounded allow-listed summary; never surface payloads or process output."""

        path = (
            Path(self.config.output_root)
            / "scheduled"
            / "decision_evidence_capture"
            / "latest_status.json"
        )
        if not path.is_file():
            return WorkbenchLatestCaptureStatus()
        try:
            if path.stat().st_size > _CAPTURE_STATUS_MAX_BYTES:
                return WorkbenchLatestCaptureStatus()
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return WorkbenchLatestCaptureStatus()
        if not isinstance(payload, dict):
            return WorkbenchLatestCaptureStatus()
        raw_status = payload.get("status")
        if (
            payload.get("schema_version") != _CAPTURE_STATUS_SCHEMA
            or payload.get("task") != _CAPTURE_STATUS_TASK
            or payload.get("finalized") is not True
            or not isinstance(raw_status, str)
            or raw_status not in {"passed", "failed", "degraded"}
        ):
            return WorkbenchLatestCaptureStatus()

        raw_run_id = payload.get("run_id")
        if not isinstance(raw_run_id, str) or not _CAPTURE_RUN_ID_RE.fullmatch(raw_run_id):
            return WorkbenchLatestCaptureStatus()
        decision_date = _canonical_iso_date(payload.get("decision_date"))
        if decision_date is None or decision_date > evaluation_date:
            return WorkbenchLatestCaptureStatus()

        raw_saved = payload.get("snapshot_saved")
        snapshot_saved = raw_saved if type(raw_saved) is bool else None
        raw_duplicate = payload.get("snapshot_duplicate")
        snapshot_duplicate = raw_duplicate if type(raw_duplicate) is bool else None
        raw_failures = payload.get("failure_reasons")
        failures = (
            tuple(item for item in raw_failures if isinstance(item, str))
            if isinstance(raw_failures, list)
            else ()
        )
        snapshot_failures = tuple(
            reason
            for reason in failures
            if reason.startswith(
                (
                    "snapshot_cli_",
                    "snapshot_json_",
                    "snapshot_not_saved",
                    "snapshot_confirm_",
                    "snapshot_persisted_",
                )
            )
        )
        if any("timeout" in reason.lower() for reason in snapshot_failures):
            return WorkbenchLatestCaptureStatus(
                status="timeout",
                run_id=raw_run_id,
                decision_date=decision_date,
                failure_reason="snapshot_cli_timeout",
                snapshot_saved=snapshot_saved,
            )
        if snapshot_saved is True or snapshot_duplicate is True:
            return WorkbenchLatestCaptureStatus(
                status="saved",
                run_id=raw_run_id,
                decision_date=decision_date,
                snapshot_saved=snapshot_saved,
            )
        if snapshot_saved is False and snapshot_failures:
            return WorkbenchLatestCaptureStatus(
                status="failed",
                run_id=raw_run_id,
                decision_date=decision_date,
                failure_reason="snapshot_capture_failed",
                snapshot_saved=False,
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
