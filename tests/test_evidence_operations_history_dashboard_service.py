from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from app_module.evidence_operations_history_dashboard_dtos import EvidenceOperationsHistoryDashboardRequest
from app_module.evidence_operations_history_dashboard_service import (
    EvidenceOperationsHistoryDashboardService,
    create_evidence_operations_history_dashboard_service,
)
from app_module.evidence_operations_history_repository import EvidenceOperationsHistoryRepository
from app_module.evidence_operations_service import EvidenceOperationsService
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "evidence-ops-history-dashboard.db"
    config.use_sqlite = True
    return config


def _readiness(*args, **kwargs) -> dict[str, object]:
    return {
        "readiness": "ready_for_manual_confirm",
        "blocking_gaps": ["manual_smoke_missing"],
        "warnings": ["sample_pending"],
        "required_manual_checks": ["manual evidence review"],
        "production_scheduler_allowed": False,
        "latest_smoke_status": "pending",
        "working_copy_confirm_passed": False,
    }


def _history_record(index: int, *, period_start: str = "2026-07-06", period_end: str = "2026-07-12"):
    return SimpleNamespace(
        period_start=period_start,
        period_end=period_end,
        review_status="needs_manual_review" if index % 2 else "coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=0,
        manual_lifecycle_candidate_count=0,
        warnings_count=index % 3,
        review_id=f"review-{index}",
        review_hash="sha256:" + f"{index:064x}",
        created_at="2026-07-13T00:00:00Z",
    )


class _HistoryBackend:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def list_weekly_reviews(self, **kwargs):
        self.calls.append(kwargs)
        records = [
            record
            for record in self.records
            if (kwargs["start_date"] is None or record.period_end >= kwargs["start_date"])
            and (kwargs["end_date"] is None or record.period_start <= kwargs["end_date"])
        ]
        cursor = kwargs.get("cursor")
        if cursor is not None:
            records = [
                record for record in records
                if (record.period_end, record.period_start, record.review_id)
                > (cursor[0], cursor[1], cursor[2])
            ]
        return records[: kwargs["limit"]]


def test_history_dashboard_fetches_one_extra_row_and_discloses_truncated_scope() -> None:
    backend = _HistoryBackend([_history_record(index) for index in range(51)])

    result = EvidenceOperationsHistoryDashboardService(backend).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest()
    )

    assert backend.calls[0]["limit"] == 51
    assert len(result.rows) == 50
    assert result.has_more_rows is True
    assert result.cards.reviews_count == 50
    assert result.cards.warnings_count == sum(row.warnings_count for row in result.rows)


def test_history_dashboard_exact_limit_is_complete_and_cards_use_displayed_rows() -> None:
    backend = _HistoryBackend([_history_record(index) for index in range(50)])

    result = EvidenceOperationsHistoryDashboardService(backend).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest()
    )

    assert backend.calls[0]["limit"] == 51
    assert len(result.rows) == 50
    assert result.has_more_rows is False
    assert result.cards.reviews_count == len(result.rows)
    assert result.cards.needs_manual_review_count == sum(
        row.review_status == "needs_manual_review" for row in result.rows
    )


def test_history_dashboard_date_filter_applies_before_display_limit_and_card_aggregation() -> None:
    backend = _HistoryBackend(
        [_history_record(index) for index in range(51)]
        + [_history_record(100, period_start="2026-08-03", period_end="2026-08-09")]
    )

    result = EvidenceOperationsHistoryDashboardService(backend).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest(start_date="2026-07-01", end_date="2026-07-31")
    )

    assert backend.calls[0]["start_date"] == "2026-07-01"
    assert backend.calls[0]["end_date"] == "2026-07-31"
    assert len(result.rows) == 50
    assert all(row.period_end == "2026-07-12" for row in result.rows)
    assert result.has_more_rows is True
    assert result.cards.reviews_count == 50
    assert result.cards.warnings_count == sum(row.warnings_count for row in result.rows)


def test_history_dashboard_loads_saved_reviews_without_enabling_scheduler(tmp_path: Path) -> None:
    config = _config(tmp_path)
    weekly = EvidenceOperationsService(config, readiness_evaluator=_readiness).build_weekly_review(
        start_date="2026-07-06",
        end_date="2026-07-12",
    )
    record = EvidenceOperationsHistoryRepository(config).save_weekly_review(weekly, generated_by="test")

    result = EvidenceOperationsHistoryDashboardService(EvidenceOperationsHistoryRepository(config)).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest(start_date="2026-07-01", end_date="2026-07-31")
    )

    assert result.cards.reviews_count == 1
    assert result.source_available is True
    assert result.has_more_rows is False
    assert result.cards.production_scheduler_allowed_count == 0
    assert result.rows[0].period_end == "2026-07-12"
    assert result.rows[0].review_hash == record.review_hash
    assert result.rows[0].production_scheduler_allowed is False
    assert "不會啟用 production scheduler" in " ".join(result.limitations)


def test_history_dashboard_empty_state_is_explicit(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = EvidenceOperationsHistoryDashboardService(EvidenceOperationsHistoryRepository(config)).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest()
    )

    assert result.rows == ()
    assert result.source_available is True
    assert result.cards.reviews_count == 0
    assert result.cards.warnings_count == 0
    assert "尚無 weekly review history" in result.empty_state_message


def test_history_dashboard_factory_is_query_only_when_db_is_missing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    missing_db = tmp_path / "missing" / "evidence-ops-history.db"
    config.db_file = missing_db

    service = create_evidence_operations_history_dashboard_service(config)
    result = service.load_dashboard(EvidenceOperationsHistoryDashboardRequest())

    assert result.rows == ()
    assert result.source_available is False
    assert "目前只讀資料源不可用" in result.empty_state_message
    assert "evidence_operations_history_db_missing" in result.empty_state_message
    assert not missing_db.exists()
    assert not missing_db.parent.exists()


def test_history_dashboard_factory_marks_existing_database_without_history_table_unavailable(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    missing_table_db = tmp_path / "existing-without-history-table.db"
    with sqlite3.connect(missing_table_db):
        pass
    config.db_file = missing_table_db

    result = create_evidence_operations_history_dashboard_service(config).load_dashboard(
        EvidenceOperationsHistoryDashboardRequest()
    )

    assert result.rows == ()
    assert result.source_available is False
    assert "evidence_operations_history_table_missing" in result.empty_state_message
    assert missing_table_db.exists()


def test_history_dashboard_reads_three_sqlite_pages_with_stable_ties_and_page_cards(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repository = EvidenceOperationsHistoryRepository(config)
    with sqlite3.connect(config.db_file) as connection:
        connection.executemany(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES (?, ?, '2026-07-06', '2026-07-12', 'coverage_only',
                    'ready_for_manual_confirm', 0, 0, 0, 0, ?, 'test', '{}')""",
            [
                (f"review-{index:03d}", f"hash-{index:03d}", index % 4)
                for index in range(111)
            ],
        )
        connection.execute(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES ('other-period', 'hash-other-period', '2026-08-03', '2026-08-09', 'needs_manual_review',
                    'ready_for_manual_confirm', 0, 0, 0, 0, 99, 'test', '{}')"""
        )
    service = EvidenceOperationsHistoryDashboardService(repository)
    request = EvidenceOperationsHistoryDashboardRequest(start_date="2026-07-01", end_date="2026-07-31")

    first = service.load_dashboard(request)
    second = service.load_dashboard(
        EvidenceOperationsHistoryDashboardRequest(
            start_date=request.start_date, end_date=request.end_date, cursor=first.next_cursor
        )
    )
    third = service.load_dashboard(
        EvidenceOperationsHistoryDashboardRequest(
            start_date=request.start_date, end_date=request.end_date, cursor=second.next_cursor
        )
    )

    assert [len(page.rows) for page in (first, second, third)] == [50, 50, 11]
    assert [page.has_more_rows for page in (first, second, third)] == [True, True, False]
    all_ids = [row.review_id for page in (first, second, third) for row in page.rows]
    assert all_ids == [f"review-{index:03d}" for index in range(111)]
    assert len(set(all_ids)) == 111
    assert first.cards.reviews_count == 50
    assert first.cards.warnings_count == sum(row.warnings_count for row in first.rows)
    assert first.next_cursor is not None
    assert second.next_cursor is not None
    assert third.next_cursor is None


def test_history_dashboard_page_cursor_excludes_newer_rows_appended_after_first_page(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repository = EvidenceOperationsHistoryRepository(config)
    with sqlite3.connect(config.db_file) as connection:
        connection.executemany(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES (?, ?, '2026-07-06', '2026-07-12', 'coverage_only',
                    'ready_for_manual_confirm', 0, 0, 0, 0, 0, 'test', '{}')""",
            [
                (f"review-{index:03d}", f"hash-{index:03d}")
                for index in range(60)
            ],
        )
    service = EvidenceOperationsHistoryDashboardService(repository)
    first = service.load_dashboard(EvidenceOperationsHistoryDashboardRequest())
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES ('newest', 'hash-newest', '2026-07-13', '2026-07-19', 'coverage_only',
                    'ready_for_manual_confirm', 0, 0, 0, 0, 0, 'test', '{}')"""
        )

    second = service.load_dashboard(EvidenceOperationsHistoryDashboardRequest(cursor=first.next_cursor))
    assert [row.review_id for row in first.rows[:2]] == ["review-000", "review-001"]
    assert [row.review_id for row in second.rows] == [f"review-{index:03d}" for index in range(50, 60)]
    assert set(row.review_id for row in first.rows).isdisjoint(row.review_id for row in second.rows)
