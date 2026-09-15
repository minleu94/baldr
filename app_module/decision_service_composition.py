"""MainWindow 使用的 Decision service composition root。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app_module.decision_data_providers import (
    industry_index_frame_provider,
    market_index_frame_provider,
    recent_industry_screen_provider,
    recent_stock_screen_provider,
)
from app_module.application_ports import MarketFrameProvider
from data_module.pit_sector_membership_reader import PITSectorMembershipReader


@dataclass(frozen=True)
class DecisionServiceComposition:
    config: Any
    industry_mapper: Any
    screening_service: Any
    regime_service: Any
    recommendation_service: Any
    industry_strength_service: Any = None


def _default_dependencies() -> dict[str, Any]:
    from app_module.recommendation_service import RecommendationService
    from app_module.regime_service import RegimeService
    from app_module.screening_service import ScreeningService
    from app_module.industry_strength_service import IndustryStrengthService
    from decision_module.industry_mapper import IndustryMapper
    from decision_module.market_regime_detector import MarketRegimeDetector
    from decision_module.stock_screener import StockScreener

    return {
        "IndustryMapper": IndustryMapper,
        "ScreeningService": ScreeningService,
        "IndustryStrengthService": IndustryStrengthService,
        "MarketRegimeDetector": MarketRegimeDetector,
        "RegimeService": RegimeService,
        "RecommendationService": RecommendationService,
        "StockScreener": StockScreener,
    }


def build_decision_service_composition(
    *,
    config: Any,
    dependencies: Mapping[str, Any] | None = None,
    industry_index_provider: MarketFrameProvider | None = None,
    market_index_provider: MarketFrameProvider | None = None,
    pit_membership_reader: PITSectorMembershipReader | None = None,
) -> DecisionServiceComposition:
    """建立共享 mapper 與各自獨立的 regime detector。"""
    constructors = dict(dependencies or _default_dependencies())
    industry_provider = (
        industry_index_provider
        if industry_index_provider is not None
        else industry_index_frame_provider(config)
    )
    market_provider = (
        market_index_provider
        if market_index_provider is not None
        else market_index_frame_provider(config)
    )
    mapper = constructors["IndustryMapper"](
        config, industry_index_provider=industry_provider
    )
    active_pit_reader = pit_membership_reader or _configured_pit_reader(config)
    stock_screener = constructors["StockScreener"](
        config,
        mapper,
        recent_stock_provider=recent_stock_screen_provider(config),
        recent_industry_provider=recent_industry_screen_provider(config),
    )
    screening_kwargs: dict[str, Any] = {
        "industry_mapper": mapper,
        "stock_screener": stock_screener,
    }
    industry_strength_service = None
    if "IndustryStrengthService" in constructors:
        try:
            industry_strength_kwargs: dict[str, Any] = {}
            if active_pit_reader is not None:
                industry_strength_kwargs["pit_membership_reader"] = active_pit_reader
                configured_market_scope = getattr(config, "pit_market_scope", None)
                if configured_market_scope:
                    industry_strength_kwargs["pit_market_scope"] = configured_market_scope
            industry_strength_service = constructors["IndustryStrengthService"](
                config,
                **industry_strength_kwargs,
            )
            screening_kwargs["industry_strength_service"] = industry_strength_service
        except Exception:
            # 產業強弱是可降級的研究 read model；保留既有篩選服務契約。
            pass
    screening_service = constructors["ScreeningService"](config, **screening_kwargs)
    regime_detector = constructors["MarketRegimeDetector"](
        config, market_frame_provider=market_provider
    )
    recommendation_detector = constructors["MarketRegimeDetector"](
        config, market_frame_provider=market_provider
    )
    regime_service = constructors["RegimeService"](
        config, regime_detector=regime_detector
    )
    recommendation_kwargs: dict[str, Any] = {
        "industry_mapper": mapper,
        "regime_detector": recommendation_detector,
    }
    if active_pit_reader is not None:
        recommendation_kwargs["pit_membership_reader"] = active_pit_reader
    # The normal application composition explicitly injects the read-only
    # calibration consumer.  Test/custom service constructors keep the legacy
    # dependency contract and may opt in themselves.
    if dependencies is None:
        from app_module.recommendation_calibration_consumer import (
            build_default_recommendation_calibration_consumer,
        )

        calibration_consumer = build_default_recommendation_calibration_consumer(config)
        if calibration_consumer is not None:
            recommendation_kwargs["calibration_consumer"] = calibration_consumer
    recommendation_service = constructors["RecommendationService"](
        config,
        **recommendation_kwargs,
    )
    return DecisionServiceComposition(
        config=config,
        industry_mapper=mapper,
        screening_service=screening_service,
        regime_service=regime_service,
        recommendation_service=recommendation_service,
        industry_strength_service=industry_strength_service,
    )


def _configured_pit_reader(config: Any) -> PITSectorMembershipReader | None:
    """只在 config 明確指定 artifact path 時組合 PIT reader。"""

    configured = getattr(config, "pit_sector_membership_paths", None)
    if configured is None:
        configured = getattr(config, "pit_sector_membership_path", None)
    if not configured:
        return None
    return PITSectorMembershipReader.from_config(config)
