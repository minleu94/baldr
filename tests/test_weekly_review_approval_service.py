from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app_module.approved_weekly_history_projection import load_approved_weekly_history_projection
from app_module.weekly_review_approval_service import WeeklyReviewApprovalService


@dataclass(frozen=True)
class _HistoryRecord:
    review_id: str
    review_hash: str
    period_start: str
    period_end: str


class _HistoryRepository:
    def __init__(self, record: _HistoryRecord | None) -> None:
        self.record = record

    def get_weekly_review(self, review_id: str) -> _HistoryRecord | None:
        if self.record is not None and self.record.review_id == review_id:
            return self.record
        return None


def _service() -> WeeklyReviewApprovalService:
    return WeeklyReviewApprovalService(
        _HistoryRepository(
            _HistoryRecord(
                review_id="eor_01",
                review_hash="sha256:" + "a" * 64,
                period_start="2026-10-19",
                period_end="2026-10-25",
            )
        )
    )


def _approve(service: WeeklyReviewApprovalService, path: Path, **overrides):
    values = {
        "projection_path": path,
        "review_id": "eor_01",
        "review_hash": "sha256:" + "a" * 64,
        "period_start": "2026-10-19",
        "period_end": "2026-10-25",
        "owner_name": "林研究員",
        "owner_role": "portfolio_owner",
        "approved_at": "2026-10-26T12:00:00Z",
    }
    values.update(overrides)
    return service.approve_weekly_review(**values)


def test_owner_approval_appends_pinned_projection_and_keeps_credit_disabled(tmp_path: Path) -> None:
    projection = tmp_path / "approval.json"

    result = _approve(_service(), projection)

    assert result.saved is True
    assert result.error_code == ""
    assert result.record is not None
    assert result.record["review_hash"] == "sha256:" + "a" * 64
    assert result.record["status"] == "approved_weekly_review"
    loaded = load_approved_weekly_history_projection(projection)
    assert loaded is not None
    assert len(loaded.records) == 1
    assert loaded.records[0]["review_id"] == result.record["review_id"]
    assert loaded.records[0]["review_hash"] == result.record["review_hash"]
    payload = json.loads(projection.read_text(encoding="utf-8"))
    assert payload["formal_credit_authorized"] is False
    assert payload["records"][0]["owner_name"] == "林研究員"


def test_owner_note_is_saved_and_preserved_on_later_append(tmp_path: Path) -> None:
    projection = tmp_path / "approval.json"
    noted_service = WeeklyReviewApprovalService(
        _HistoryRepository(
            _HistoryRecord(
                review_id="eor_01",
                review_hash="sha256:" + "a" * 64,
                period_start="2026-10-19",
                period_end="2026-10-25",
            )
        ),
        projection,
    )
    result = noted_service.approve_weekly_review(
        review_id="eor_01",
        review_hash="sha256:" + "a" * 64,
        period_start="2026-10-19",
        period_end="2026-10-25",
        owner_name="林研究員",
        owner_role="portfolio_owner",
        approved_at="2026-10-26T12:00:00Z",
        review_note="核對本期報告及來源摘要。",
    )

    assert result.saved is True
    assert result.record is not None
    assert result.record["review_note"] == "核對本期報告及來源摘要。"
    raw = json.loads(projection.read_text(encoding="utf-8"))
    assert raw["records"][0]["review_note"] == "核對本期報告及來源摘要。"
    loaded = load_approved_weekly_history_projection(projection)
    assert loaded is not None
    assert loaded.records[0]["review_hash"] == "sha256:" + "a" * 64


def test_approval_preserves_prior_period_records(tmp_path: Path) -> None:
    projection = tmp_path / "approval.json"
    projection.write_text(
        json.dumps(
            {
                "schema_version": "approved-weekly-history-projection.v1",
                "formal_credit_authorized": False,
                "records": [
                    {
                        "review_id": "eor_00",
                        "review_hash": "sha256:" + "b" * 64,
                        "period_start": "2026-10-12",
                        "period_end": "2026-10-18",
                        "owner_role": "portfolio_owner",
                        "approved_at": "2026-10-19T12:00:00Z",
                        "status": "approved_weekly_review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _approve(_service(), projection)

    assert result.saved is True
    loaded = load_approved_weekly_history_projection(projection)
    assert loaded is not None
    assert len(loaded.records) == 2
    assert loaded.records[0]["review_id"] == "eor_00"
    assert loaded.records[1]["review_id"] == "eor_01"


def test_approval_rejects_missing_owner_role(tmp_path: Path) -> None:
    result = _approve(_service(), tmp_path / "approval.json", owner_role="  ")

    assert result.saved is False
    assert result.error_code == "owner_role_required"


def test_approval_rejects_missing_owner_name(tmp_path: Path) -> None:
    result = _approve(_service(), tmp_path / "approval.json", owner_name="  ")

    assert result.saved is False
    assert result.error_code == "owner_name_required"


def test_approval_rejects_missing_history_and_stale_hash_or_period(tmp_path: Path) -> None:
    missing = WeeklyReviewApprovalService(_HistoryRepository(None))
    missing_result = _approve(missing, tmp_path / "missing.json")
    stale_result = _approve(
        _service(),
        tmp_path / "stale.json",
        review_hash="sha256:" + "c" * 64,
    )
    period_result = _approve(
        _service(),
        tmp_path / "stale-period.json",
        period_end="2026-10-26",
    )

    assert missing_result.error_code == "history_record_missing"
    assert stale_result.error_code == "history_pin_mismatch"
    assert period_result.error_code == "history_pin_mismatch"
    assert not (tmp_path / "stale.json").exists()


def test_approval_rejects_second_approval_for_same_period_without_overwrite(tmp_path: Path) -> None:
    projection = tmp_path / "approval.json"
    first = _approve(_service(), projection)
    before = projection.read_bytes()
    second = _approve(_service(), projection)

    assert first.saved is True
    assert second.saved is False
    assert second.error_code == "period_already_approved"
    assert projection.read_bytes() == before


def test_approval_rejects_different_hash_for_already_approved_period(tmp_path: Path) -> None:
    projection = tmp_path / "approval.json"
    _approve(_service(), projection)
    second = _approve(
        _service(),
        projection,
        review_hash="sha256:" + "d" * 64,
    )

    assert second.saved is False
    assert second.error_code == "history_pin_mismatch"


def test_approval_rejects_formal_database_path(tmp_path: Path) -> None:
    result = _approve(_service(), tmp_path / "twstock.db")

    assert result.saved is False
    assert result.error_code == "formal_database_path_forbidden"
    assert not (tmp_path / "twstock.db").exists()


def test_approval_rejects_timezone_free_timestamp(tmp_path: Path) -> None:
    result = _approve(
        _service(),
        tmp_path / "approval.json",
        approved_at="2026-10-26T12:00:00",
    )

    assert result.saved is False
    assert result.error_code == "approved_at_timezone_required"
    assert not (tmp_path / "approval.json").exists()
