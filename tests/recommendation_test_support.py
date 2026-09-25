"""明示建立 RecommendationService 測試用 source composition。"""

from __future__ import annotations

from typing import Any

from app_module.recommendation_service import RecommendationService


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
