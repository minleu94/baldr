from types import SimpleNamespace
from unittest.mock import MagicMock

from app_module.decision_service_composition import (
    build_decision_service_composition,
    build_industry_mapper,
)


def test_decision_service_composition_injects_shared_mapper_and_data_ports() -> None:
    dependencies = {
        name: MagicMock(name=name)
        for name in (
            "IndustryMapper",
            "ScreeningService",
            "MarketRegimeDetector",
            "RegimeService",
            "RecommendationService",
            "StockScreener",
        )
    }
    dependencies["IndustryMapper"].return_value = mapper = object()
    dependencies["MarketRegimeDetector"].return_value = regime_detector = object()
    dependencies["StockScreener"].return_value = stock_screener = object()
    industry_provider = lambda: None
    companies_provider = lambda: None
    market_provider = object()

    composition = build_decision_service_composition(
        config=SimpleNamespace(),
        dependencies=dependencies,
        companies_provider=companies_provider,
        industry_index_provider=industry_provider,
        market_index_provider=market_provider,
    )

    dependencies["IndustryMapper"].assert_called_once_with(
        composition.config,
        industry_index_provider=industry_provider,
        companies_provider=companies_provider,
    )
    dependencies["ScreeningService"].assert_called_once_with(
        composition.config, industry_mapper=mapper, stock_screener=stock_screener
    )
    stock_screener_kwargs = dependencies["StockScreener"].call_args.kwargs
    assert callable(stock_screener_kwargs["recent_stock_provider"])
    assert callable(stock_screener_kwargs["recent_industry_provider"])
    assert callable(stock_screener_kwargs["stock_fallback_provider"])
    assert callable(stock_screener_kwargs["industry_fallback_provider"])
    dependencies["MarketRegimeDetector"].assert_called_once_with()
    dependencies["RegimeService"].assert_called_once_with(
        composition.config,
        regime_detector=regime_detector,
        use_persistent_history=True,
        market_frame_provider=market_provider,
    )
    dependencies["RecommendationService"].assert_called_once()
    recommendation_args = dependencies["RecommendationService"].call_args
    assert recommendation_args.args == (composition.config,)
    assert recommendation_args.kwargs["industry_mapper"] is mapper
    assert recommendation_args.kwargs["regime_service"] is dependencies[
        "RegimeService"
    ].return_value
    assert recommendation_args.kwargs["input_preparer"] is not None


def test_normal_composition_injects_read_only_recommendation_calibration_consumer(monkeypatch) -> None:
    dependencies = {
        name: MagicMock(name=name)
        for name in (
            "IndustryMapper",
            "ScreeningService",
            "MarketRegimeDetector",
            "RegimeService",
            "RecommendationService",
            "StockScreener",
        )
    }
    dependencies["IndustryMapper"].return_value = object()
    dependencies["MarketRegimeDetector"].return_value = object()
    dependencies["StockScreener"].return_value = object()
    consumer = object()
    monkeypatch.setattr(
        "app_module.recommendation_calibration_consumer.build_default_recommendation_calibration_consumer",
        lambda config: consumer,
    )
    monkeypatch.setattr(
        "app_module.decision_service_composition._default_dependencies",
        lambda: dependencies,
    )

    config = SimpleNamespace()
    build_decision_service_composition(
        config=config,
        industry_index_provider=lambda: None,
        market_index_provider=object(),
    )

    kwargs = dependencies["RecommendationService"].call_args.kwargs
    assert kwargs["calibration_consumer"] is consumer


def test_legacy_mapper_composition_injects_explicit_company_and_index_providers() -> None:
    constructor = MagicMock(return_value="mapper")
    config = SimpleNamespace()
    company_frame_provider = lambda: None
    index_frame_provider = lambda: None

    result = build_industry_mapper(
        config,
        constructor=constructor,
        companies_provider=company_frame_provider,
        industry_index_provider=index_frame_provider,
    )

    assert result == "mapper"
    constructor.assert_called_once_with(
        config,
        industry_index_provider=index_frame_provider,
        companies_provider=company_frame_provider,
    )
