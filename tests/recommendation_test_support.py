"""明示建立 RecommendationService 測試用 source composition。"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

from app_module.recommendation_service import RecommendationService


class _TestMarketSessionCadence:
    """Test-only verified calendar double; session policy has dedicated tests."""

    def __init__(self, clock: Any) -> None:
        self.clock = clock

    def assess(self, decision_date: date, actual_date: date) -> Any:
        return SimpleNamespace(
            status="current",
            expected_date=actual_date,
            metadata={
                "decision_date": decision_date.isoformat(),
                "actual_date": actual_date.isoformat(),
                "cutoff_policy": "test_verified_session",
                "historical_pit": False,
                "blockers": [],
                "calendar": {"status": "verified_test_double"},
            },
        )


def build_recommendation_test_preparer(
    config: Any,
    *,
    market_data_provider: Any = None,
    pit_membership_reader: Any = None,
) -> Any:
    """建立隔離測試的 input preparer；呼叫端須明確傳給 service。"""

    from app_module.recommendation.input_preparation import (
        build_default_recommendation_input_preparer,
    )

    return build_default_recommendation_input_preparer(
        config,
        market_data_provider=market_data_provider,
        pit_membership_reader=pit_membership_reader,
        market_session_cadence_factory=(
            lambda _config, *, clock: _TestMarketSessionCadence(clock)
        ),
    )


def build_recommendation_test_service(config: Any, **kwargs: Any) -> RecommendationService:
    """Opt-in service factory for tests; never installed as a global patch."""

    return RecommendationService(
        config,
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=kwargs.get("market_data_provider"),
            pit_membership_reader=kwargs.get("pit_membership_reader"),
        ),
        **kwargs,
    )
