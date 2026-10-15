from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from app_module.recommendation_service import RecommendationService


class _CohortContextSession:
    def __init__(self, source_context: dict[str, Any]) -> None:
        self.source_context = source_context

    def daily_monthly_cohort_source_context(self) -> dict[str, Any]:
        return deepcopy(self.source_context)


def test_current_monthly_context_preserves_pin_hash_and_unknown_partial_outcomes() -> None:
    cohort_sha256 = "a" * 64
    pin = {
        "schema_version": "daily-monthly-revenue-cohort-pin.v1",
        "cohort_sha256": cohort_sha256,
        "market_pins": [
            {
                "market": "twse",
                "batch_id": "daily-twse-2026-10-14",
                "manifest_sha256": "b" * 64,
                "receipt_sha256": "c" * 64,
            }
        ],
    }
    source_context = {
        "schema_version": "recommendation-daily-monthly-cohort-context.v1",
        "cohort_sha256": cohort_sha256,
        "pin": pin,
        "invocation_frozen_at": "2026-10-14T16:30:00+00:00",
        "read_outcome_by_stock": {
            "1101": "partial",
            "2330": "unknown",
            "4130": "unavailable",
            "5871": "missing",
        },
        "source_scope": "current_observed_only",
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
    }
    target_context: dict[str, Any] = {
        "fundamental_inputs": [],
        "current_observation_cutoff_at": source_context["invocation_frozen_at"],
    }

    RecommendationService._record_daily_monthly_revenue_cohort_context(
        input_session=_CohortContextSession(source_context),  # type: ignore[arg-type]
        target_context=target_context,
    )

    saved = target_context["daily_monthly_revenue_cohort"]
    assert saved == source_context
    assert saved["cohort_sha256"] == cohort_sha256
    assert saved["pin"] == pin
    assert saved["read_outcome_by_stock"] == {
        "1101": "partial",
        "2330": "unknown",
        "4130": "unavailable",
        "5871": "missing",
    }
    assert saved["source_scope"] == "current_observed_only"
    assert saved["historical_pit_eligible"] is False
    assert saved["formal_pit_eligible"] is False
    assert "qualified" not in saved

    source_context["read_outcome_by_stock"]["2330"] = "mutated_after_read"
    assert saved["read_outcome_by_stock"]["2330"] == "unknown"


def test_empty_or_legacy_source_context_leaves_existing_context_unchanged() -> None:
    target_context: dict[str, Any] = {
        "fundamental_inputs": [{"metric": "monthly_revenue", "value": "10"}],
        "current_observation_cutoff_at": "2026-10-14T16:30:00+00:00",
    }
    before = deepcopy(target_context)

    RecommendationService._record_daily_monthly_revenue_cohort_context(
        input_session=_CohortContextSession({}),  # type: ignore[arg-type]
        target_context=target_context,
    )
    RecommendationService._record_daily_monthly_revenue_cohort_context(
        input_session=object(),  # type: ignore[arg-type]  # 舊 session 沒有 metadata API。
        target_context=target_context,
    )

    assert target_context == before
    assert "daily_monthly_revenue_cohort" not in target_context


def test_historical_monthly_route_does_not_read_or_attach_cohort_context() -> None:
    calls: list[tuple[str, date]] = []

    class _HistoricalOnlySession:
        def load_monthly_revenues(
            self, *, stock_code: str, decision_date: date
        ) -> tuple[str, ...]:
            calls.append((stock_code, decision_date))
            return ("historical-provider-result",)

        def daily_monthly_cohort_source_context(self) -> dict[str, Any]:
            raise AssertionError("historical route must not read current cohort metadata")

    target_context: dict[str, Any] = {"fundamental_inputs": []}
    service = RecommendationService.__new__(RecommendationService)
    result = service._load_governed_monthly_revenues(
        input_session=_HistoricalOnlySession(),  # type: ignore[arg-type]
        stock_code="2330",
        decision_date=date(2026, 10, 14),
    )

    assert result == ("historical-provider-result",)
    assert calls == [("2330", date(2026, 10, 14))]
    assert target_context == {"fundamental_inputs": []}

