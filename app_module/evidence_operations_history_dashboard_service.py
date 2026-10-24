from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardCards,
    EvidenceOperationsHistoryCursor,
    EvidenceOperationsHistoryDashboardRequest,
    EvidenceOperationsHistoryDashboardResult,
    EvidenceOperationsHistoryDashboardRow,
)
from app_module.evidence_operations_history_repository import (
    EvidenceOperationsHistoryReadOnlyError,
    EvidenceOperationsHistoryRepository,
)


class EvidenceOperationsHistoryDashboardService:
    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def load_dashboard(
        self,
        request: EvidenceOperationsHistoryDashboardRequest,
    ) -> EvidenceOperationsHistoryDashboardResult:
        diagnostics: tuple[str, ...] = ()
        source_available = True
        row_limit = min(50, max(1, int(request.limit)))
        has_more_rows = False
        next_cursor = None
        try:
            query: dict[str, Any] = {
                "start_date": _blank_to_none(request.start_date),
                "end_date": _blank_to_none(request.end_date),
                "limit": row_limit + 1,
            }
            if request.cursor is not None:
                query["cursor"] = (
                    request.cursor.period_end,
                    request.cursor.period_start,
                    request.cursor.review_id,
                )
            queried_records = tuple(self.backend.list_weekly_reviews(**query))
            has_more_rows = len(queried_records) > row_limit
            records = queried_records[:row_limit]
            if has_more_rows and records:
                last_record = records[-1]
                next_cursor = EvidenceOperationsHistoryCursor(
                    period_end=str(last_record.period_end),
                    period_start=str(last_record.period_start),
                    review_id=str(last_record.review_id),
                )
        except EvidenceOperationsHistoryReadOnlyError as exc:
            # A missing history DB/table is an expected read-only state.  Do
            # not let a dashboard refresh create a schema just to render 0.
            records = ()
            diagnostics = (str(exc),)
            source_available = False
        rows = tuple(_row_from_record(record) for record in records)
        return EvidenceOperationsHistoryDashboardResult(
            request=request,
            cards=_cards_from_rows(rows),
            rows=rows,
            empty_state_message=_empty_state_message(rows, diagnostics=diagnostics),
            source_available=source_available,
            has_more_rows=has_more_rows,
            next_cursor=next_cursor,
        )


def create_evidence_operations_history_dashboard_service(
    config: Any,
    *,
    db_path: str | Path | None = None,
) -> EvidenceOperationsHistoryDashboardService:
    return EvidenceOperationsHistoryDashboardService(
        EvidenceOperationsHistoryRepository(config, db_path=db_path, read_only=True)
    )


def _row_from_record(record: Any) -> EvidenceOperationsHistoryDashboardRow:
    return EvidenceOperationsHistoryDashboardRow(
        period_start=str(record.period_start),
        period_end=str(record.period_end),
        review_status=str(record.review_status),
        scheduler_readiness=str(record.scheduler_readiness),
        production_scheduler_allowed=bool(record.production_scheduler_allowed),
        decision_quality_reviews_count=int(record.decision_quality_reviews_count),
        signal_decay_observations_count=int(record.signal_decay_observations_count),
        manual_lifecycle_candidate_count=int(record.manual_lifecycle_candidate_count),
        warnings_count=int(record.warnings_count),
        review_id=str(record.review_id),
        created_at=str(record.created_at),
    )


def _cards_from_rows(rows: tuple[EvidenceOperationsHistoryDashboardRow, ...]) -> EvidenceOperationsHistoryDashboardCards:
    statuses = Counter(row.review_status for row in rows)
    return EvidenceOperationsHistoryDashboardCards(
        reviews_count=len(rows),
        needs_manual_review_count=statuses["needs_manual_review"],
        coverage_only_count=statuses["coverage_only"],
        ready_for_closeout_count=statuses["ready_for_weekly_closeout"],
        production_scheduler_allowed_count=sum(1 for row in rows if row.production_scheduler_allowed),
        warnings_count=sum(row.warnings_count for row in rows),
    )


def _empty_state_message(
    rows: tuple[EvidenceOperationsHistoryDashboardRow, ...],
    *,
    diagnostics: tuple[str, ...] = (),
) -> str:
    if rows:
        return ""
    if diagnostics:
        return (
            "尚無 weekly review history；目前只讀資料源不可用，未建立或修改資料庫。"
            f" 診斷：{'; '.join(diagnostics)}"
        )
    return "尚無 weekly review history。請先用 CLI 產生 weekly review，並以 --save-history 封存人工覆盤紀錄。"


def _blank_to_none(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
