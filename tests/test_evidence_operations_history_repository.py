from __future__ import annotations

from pathlib import Path
import sqlite3

from app_module.evidence_operations_history_repository import EvidenceOperationsHistoryRepository
from app_module.evidence_operations_service import EvidenceOperationsService
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "evidence-ops-history.db"
    config.use_sqlite = True
    return config


def _readiness(*args, **kwargs) -> dict[str, object]:
    return {
        "readiness": "ready_for_manual_confirm",
        "blocking_gaps": [],
        "warnings": [],
        "required_manual_checks": ["manual evidence review"],
        "production_scheduler_allowed": False,
        "latest_smoke_status": "passed",
        "working_copy_confirm_passed": True,
    }


def test_history_repository_saves_weekly_review_snapshot_idempotently(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = EvidenceOperationsService(config, readiness_evaluator=_readiness)
    report = service.build_weekly_review(start_date="2026-07-06", end_date="2026-07-12")
    repo = EvidenceOperationsHistoryRepository(config)

    first = repo.save_weekly_review(report, generated_by="codex")
    second = repo.save_weekly_review(report, generated_by="codex")

    assert first.review_hash == second.review_hash
    assert first.review_id == second.review_id
    assert first.production_scheduler_allowed is False
    assert first.payload_json["status"] == "coverage_only"
    assert first.generated_by == "codex"
    rows = repo.list_weekly_reviews()
    assert [row.review_id for row in rows] == [first.review_id]


def test_history_repository_lists_latest_period_first(tmp_path: Path) -> None:
    config = _config(tmp_path)
    service = EvidenceOperationsService(config, readiness_evaluator=_readiness)
    repo = EvidenceOperationsHistoryRepository(config)

    older = service.build_weekly_review(start_date="2026-06-29", end_date="2026-07-05")
    newer = service.build_weekly_review(start_date="2026-07-06", end_date="2026-07-12")
    repo.save_weekly_review(older, generated_by="codex")
    repo.save_weekly_review(newer, generated_by="codex")

    rows = repo.list_weekly_reviews(limit=10)

    assert [row.period_end for row in rows] == ["2026-07-12", "2026-07-05"]


def test_history_repository_keyset_pages_keep_ties_and_ignore_newer_appends(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repo = EvidenceOperationsHistoryRepository(config)
    with sqlite3.connect(config.db_file) as connection:
        connection.executemany(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES (?, ?, ?, ?, 'coverage_only', 'ready_for_manual_confirm', 0, 0, 0, 0, 0, 'test', '{}')""",
            [
                (f"review-{index:03d}", f"hash-{index:03d}", "2026-07-06", "2026-07-12")
                for index in range(111)
            ],
        )

    first = repo.list_weekly_reviews(limit=51)
    assert len(first) == 51
    assert [row.review_id for row in first[:3]] == ["review-000", "review-001", "review-002"]
    cursor = (first[49].period_end, first[49].period_start, first[49].review_id)

    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES ('review-new', 'hash-new', '2026-07-13', '2026-07-19', 'coverage_only',
                    'ready_for_manual_confirm', 0, 0, 0, 0, 0, 'test', '{}')"""
        )

    second = repo.list_weekly_reviews(limit=50, cursor=cursor)
    second_ids = [row.review_id for row in second]
    assert len(second) == 50
    assert "review-new" not in second_ids
    assert set(row.review_id for row in first[:50]).isdisjoint(second_ids)
    cursor2 = (second[-1].period_end, second[-1].period_start, second[-1].review_id)
    third = repo.list_weekly_reviews(limit=50, cursor=cursor2)
    assert [row.review_id for row in third] == [f"review-{index:03d}" for index in range(100, 111)]


def test_history_repository_keyset_cursor_preserves_date_filter(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repo = EvidenceOperationsHistoryRepository(config)
    with sqlite3.connect(config.db_file) as connection:
        connection.executemany(
            """INSERT INTO evidence_operations_weekly_reviews
            (review_id, review_hash, period_start, period_end, review_status, scheduler_readiness,
             production_scheduler_allowed, decision_quality_reviews_count, signal_decay_observations_count,
             manual_lifecycle_candidate_count, warnings_count, generated_by, payload_json)
            VALUES (?, ?, ?, ?, 'coverage_only', 'ready_for_manual_confirm', 0, 0, 0, 0, 0, 'test', '{}')""",
            [
                (f"review-{index:03d}", f"hash-{index:03d}", "2026-07-06", "2026-07-12")
                for index in range(55)
            ]
            + [("august", "hash-august", "2026-08-03", "2026-08-09")],
        )
    first = repo.list_weekly_reviews(start_date="2026-07-01", end_date="2026-07-31", limit=50)
    second = repo.list_weekly_reviews(
        start_date="2026-07-01",
        end_date="2026-07-31",
        limit=50,
        cursor=(first[-1].period_end, first[-1].period_start, first[-1].review_id),
    )
    assert len(first) == 50
    assert len(second) == 5
    assert all(row.period_end == "2026-07-12" for row in first + second)
