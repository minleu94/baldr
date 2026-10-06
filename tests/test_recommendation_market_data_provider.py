from unittest.mock import MagicMock

import pandas as pd

from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_preparer


def test_recommendation_service_uses_injected_market_history_provider() -> None:
    config = MagicMock()
    provider = MagicMock(
        return_value=pd.DataFrame(columns=["日期", "證券代號", "證券名稱"])
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=provider
        ),
    )

    result = service.run_recommendation({}, max_stocks=1, top_n=1)

    assert result == []
    provider.assert_called_once_with()
