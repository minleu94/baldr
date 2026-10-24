from __future__ import annotations

from dataclasses import replace

from app_module.decision_quality_dashboard_dtos import DecisionQualityDashboardRequest
from app_module.decision_quality_dashboard_service import DecisionQualityDashboardService
from app_module.decision_quality_dtos import DecisionQualityItem, DecisionQualityReview


class FakeDecisionQualityService:
    def __init__(self) -> None:
        self.review_calls: list[dict] = []
        self.item_calls: list[dict] = []
        self.reviews = [
            DecisionQualityReview(
                review_id="dqr-1",
                review_hash="sha256:1",
                review_period_start="2026-06-01",
                review_period_end="2026-06-30",
                review_type="monthly",
                decision_quality_score_bp=7200,
                process_adherence_score_bp=7000,
                evidence_usage_score_bp=6800,
                risk_discipline_score_bp=8000,
                review_completeness_score_bp=6000,
                review_status="needs_review",
                warnings_json=["journal_missing"],
                quality="degraded",
            )
        ]
        self.items = [
            DecisionQualityItem(
                item_id="dqi-1",
                review_id="dqr-1",
                item_type="large_live_research_gap",
                symbol="2330",
                event_date="2026-06-20",
                source_type="research_run",
                severity="medium",
                status="open",
                reason_codes_json=["large_gap_unreviewed"],
                related_gap_id="gap-1",
                related_decay_id="",
                evidence_json={"data_quality": "observed", "warnings": []},
                suggested_review_question="這個 research gap 是否需要補充覆盤？",
            )
        ]

    def list_reviews(self, **filters):
        self.review_calls.append(filters)
        rows = self.reviews
        if filters.get("start_date"):
            rows = [row for row in rows if row.review_period_end >= filters["start_date"]]
        if filters.get("end_date"):
            rows = [row for row in rows if row.review_period_start <= filters["end_date"]]
        if filters.get("review_type"):
            rows = [row for row in rows if row.review_type == filters["review_type"]]
        return rows

    def list_items(self, **filters):
        self.item_calls.append(filters)
        rows = self.items
        if filters.get("status"):
            rows = [item for item in rows if item.status == filters["status"]]
        return rows


def test_decision_quality_dashboard_filters_and_cards() -> None:
    backend = FakeDecisionQualityService()
    service = DecisionQualityDashboardService(backend)

    result = service.load_dashboard(
        DecisionQualityDashboardRequest(
            review_type="monthly",
            start_date="2026-06-01",
            end_date="2026-06-30",
            symbol="2330",
            item_type="large_live_research_gap",
            severity="medium",
            status="open",
            min_score=6000,
        )
    )

    assert backend.review_calls[-1] == {
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "review_type": "monthly",
    }
    assert backend.item_calls[-1] == {"status": "open"}
    assert result.cards.decision_quality_score == 7200
    assert result.cards.open_items == 1
    assert result.cards.reviewed_items == 0
    assert result.cards.dismissed_items == 0
    assert result.cards.warnings_count == 1
    assert result.rows[0].symbol == "2330"
    assert result.rows[0].item_type == "large_live_research_gap"
    assert "流程覆盤" in result.limitations[0]


def test_decision_quality_dashboard_empty_state_is_non_blaming() -> None:
    backend = FakeDecisionQualityService()
    backend.reviews = []
    backend.items = []

    result = DecisionQualityDashboardService(backend).load_dashboard(DecisionQualityDashboardRequest())

    assert result.rows == ()
    assert "尚無 decision quality review evidence" in result.empty_state_message
    assert "使用者錯誤" not in result.empty_state_message


def test_decision_quality_dashboard_items_follow_date_and_review_type_scope() -> None:
    backend = FakeDecisionQualityService()
    backend.reviews.extend(
        [
            DecisionQualityReview(
                review_id="dqr-weekly",
                review_hash="sha256:2",
                review_period_start="2026-06-01",
                review_period_end="2026-06-07",
                review_type="weekly",
                decision_quality_score_bp=5000,
            ),
            DecisionQualityReview(
                review_id="dqr-next-month",
                review_hash="sha256:3",
                review_period_start="2026-07-01",
                review_period_end="2026-07-31",
                review_type="monthly",
                decision_quality_score_bp=4000,
            ),
        ]
    )
    backend.items.extend(
        [
            DecisionQualityItem(
                item_id="dqi-weekly",
                review_id="dqr-weekly",
                item_type="unreviewed_signal_decay",
                symbol="2317",
                event_date="2026-06-05",
                status="reviewed",
            ),
            DecisionQualityItem(
                item_id="dqi-next-month",
                review_id="dqr-next-month",
                item_type="low_quality_data_used",
                symbol="2454",
                event_date="2026-07-20",
                status="dismissed",
            ),
        ]
    )

    result = DecisionQualityDashboardService(backend).load_dashboard(
        DecisionQualityDashboardRequest(
            review_type="monthly",
            start_date="2026-06-01",
            end_date="2026-06-30",
        )
    )

    assert result.review_count == 1
    assert result.cards.decision_quality_score == 7200
    assert result.cards.open_items == 1
    assert result.cards.reviewed_items == 0
    assert result.cards.dismissed_items == 0
    assert [row.symbol for row in result.rows] == ["2330"]


def test_decision_quality_dashboard_omits_items_when_no_review_matches() -> None:
    backend = FakeDecisionQualityService()

    result = DecisionQualityDashboardService(backend).load_dashboard(
        DecisionQualityDashboardRequest(
            review_type="weekly",
            start_date="2026-07-01",
            end_date="2026-07-31",
        )
    )

    assert result.review_count == 0
    assert result.rows == ()
    assert result.cards.open_items == 0
    assert result.cards.reviewed_items == 0
    assert result.cards.dismissed_items == 0
    assert "尚無 decision quality review evidence" in result.empty_state_message


def test_decision_quality_dashboard_portfolio_filter_uses_exact_review_identity() -> None:
    backend = FakeDecisionQualityService()
    backend.reviews[0] = replace(
        backend.reviews[0], metadata_json={"portfolio_id": "paper-main"}
    )
    backend.reviews.append(
        DecisionQualityReview(
            review_id="dqr-other-portfolio",
            review_hash="sha256:4",
            review_period_start="2026-06-01",
            review_period_end="2026-06-30",
            review_type="monthly",
            decision_quality_score_bp=3000,
            metadata_json={"portfolio_id": "paper-other"},
        )
    )
    backend.items.append(
        DecisionQualityItem(
            item_id="dqi-other-portfolio",
            review_id="dqr-other-portfolio",
            item_type="low_quality_data_used",
            symbol="2317",
            event_date="2026-06-15",
            status="reviewed",
        )
    )

    result = DecisionQualityDashboardService(backend).load_dashboard(
        DecisionQualityDashboardRequest(portfolio_id="paper-main")
    )

    assert result.review_count == 1
    assert result.cards.decision_quality_score == 7200
    assert result.cards.open_items == 1
    assert result.cards.reviewed_items == 0
    assert [row.symbol for row in result.rows] == ["2330"]


def test_decision_quality_dashboard_portfolio_filter_excludes_legacy_missing_identity() -> None:
    backend = FakeDecisionQualityService()

    result = DecisionQualityDashboardService(backend).load_dashboard(
        DecisionQualityDashboardRequest(portfolio_id="default")
    )

    assert result.review_count == 0
    assert result.rows == ()
    assert result.cards.open_items == 0
    assert "尚無 decision quality review evidence" in result.empty_state_message
