"""Decision Desk 的 Application composition root。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from pathlib import Path
from app_module.official_quote_exclusion_diagnostics import OfficialQuoteExclusionDiagnostics
from app_module.market_session_cadence import MarketSessionCadence
from app_module.decision_desk_dtos import DecisionDeskQuality, MarketRegimeSummary
from data_module.pit_sector_membership_reader import PITSectorMembershipReader


class DecisionDeskMarketRegimeProvider:
    """將既有 RegimeService 適配成 Decision Desk provider。"""

    def __init__(self, regime_service: Any):
        self.regime_service = regime_service

    @staticmethod
    def to_confidence_bp(confidence: Any) -> int | None:
        if confidence is None:
            return None
        try:
            value = Decimal(str(confidence))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if Decimal("0") <= value <= Decimal("1"):
            return int(value * Decimal("10000"))
        if Decimal("0") <= value <= Decimal("100"):
            return int(value * Decimal("100"))
        return int(value)

    def fetch_market_regime(self, as_of_date):
        if self.regime_service is None:
            return None
        try:
            as_of_date_str = as_of_date.isoformat()
            try:
                result = self.regime_service.detect_regime(as_of_date=as_of_date_str)
            except TypeError:
                result = self.regime_service.detect_regime(date=as_of_date_str)
            except Exception:
                result = self.regime_service.detect_regime(as_of_date_str)
            details = dict(getattr(result, "details", {}) or {})
            confidence_bp = self.to_confidence_bp(getattr(result, "confidence", None))
            regime_score = details.get("ma20_slope")
            if regime_score is None:
                regime_score = details.get("score")
            if regime_score is None:
                regime_score = details.get("regime_score")
            if regime_score is not None:
                try:
                    regime_score = int(Decimal(str(regime_score)) * Decimal("100"))
                except (InvalidOperation, TypeError, ValueError):
                    regime_score = None
            return MarketRegimeSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.OBSERVED,
                warnings=(),
                regime_label=getattr(result, "regime_name_cn", None)
                or getattr(result, "regime", None),
                regime_score=regime_score,
                regime_confidence=confidence_bp,
                meta=details,
            )
        except Exception:
            return None

    def fetch_market_breadth(self, as_of_date):
        return None

    def fetch_sector_rotation(self, as_of_date):
        return None

    def fetch_watchlist_triggers(self, as_of_date):
        return None

    def fetch_portfolio_alerts(self, as_of_date):
        return None


@dataclass(frozen=True)
class DecisionDeskComposition:
    builder: Any
    market_frame_loader: Any


@dataclass(frozen=True)
class SmartMoneyComposition:
    service: Any
    market_frame_loader: Any


def build_smart_money_composition(
    *,
    config: Any,
    broker_flow_service: Any,
    dependencies: dict[str, Any],
    market_frame_loader: Any = None,
    report_error: Callable[[str], None] = print,
) -> SmartMoneyComposition:
    """組裝 Smart Money semantic service，共用 Decision Desk market frame。"""
    try:
        if market_frame_loader is None:
            market_frame_loader = dependencies["DecisionMarketFrameLoader"](
                config.db_file
            )
        price_provider = dependencies["SQLiteSmartMoneyPriceProvider"](
            config.db_file,
            market_frame_loader=market_frame_loader,
        )
        service = dependencies["SmartMoneySemanticService"](
            broker_flow_service,
            price_provider=price_provider,
        )
        return SmartMoneyComposition(
            service=service,
            market_frame_loader=market_frame_loader,
        )
    except Exception as exc:  # noqa: BLE001
        report_error(
            f"[MainWindow] 決策桌面 SmartMoneySemanticService 初始化失敗：{exc}"
        )
        return SmartMoneyComposition(
            service=None,
            market_frame_loader=market_frame_loader,
        )


def build_decision_desk_composition(
    *,
    config: Any,
    regime_service: Any,
    portfolio_service: Any,
    watchlist_service: Any,
    broker_flow_service: Any = None,
    smart_money_service: Any = None,
    market_frame_loader: Any = None,
    industry_strength_service: Any = None,
    pit_membership_reader: PITSectorMembershipReader | None = None,
    dependencies: dict[str, Any],
    report_error: Callable[[str], None] = print,
) -> DecisionDeskComposition:
    """組裝可降級的 Decision Desk service graph。"""

    provider = DecisionDeskMarketRegimeProvider(regime_service)
    cadence = MarketSessionCadence.for_config(config)
    if market_frame_loader is None:
        try:
            market_frame_loader = dependencies["DecisionMarketFrameLoader"](config.db_file)
        except Exception as exc:  # noqa: BLE001
            report_error(f"[MainWindow] 決策桌面共用市場資料初始化失敗：{exc}")

    def optional_service(label: str, factory: Callable[[], Any]) -> Any:
        try:
            return factory()
        except Exception as exc:  # noqa: BLE001
            report_error(f"[MainWindow] 決策桌面 {label} 初始化失敗：{exc}")
            return None

    market_breadth_service = optional_service(
        "MarketBreadthService",
        lambda: dependencies["MarketBreadthService"](
            dependencies["SQLiteDailyPriceMarketBreadthProvider"](
                config.db_file, market_frame_loader=market_frame_loader,
                quote_diagnostics=OfficialQuoteExclusionDiagnostics(Path(config.db_file).parent.parent / "output/scheduled/daily_price_source_custody", clock=cadence.clock),
            ),
            cadence=cadence,
        ),
    )
    if industry_strength_service is None and "IndustryStrengthService" in dependencies:
        active_pit_reader = pit_membership_reader or _configured_pit_reader(config)
        industry_strength_service = optional_service(
            "IndustryStrengthService",
            lambda: dependencies["IndustryStrengthService"](
                config,
                **(
                    {
                        "pit_membership_reader": active_pit_reader,
                        **(
                            {"pit_market_scope": getattr(config, "pit_market_scope")}
                            if getattr(config, "pit_market_scope", None)
                            else {}
                        ),
                    }
                    if active_pit_reader is not None
                    else {}
                ),
            ),
        )
    sector_rotation_service = industry_strength_service
    if sector_rotation_service is None:
        sector_rotation_service = optional_service(
            "SectorRotationService",
            lambda: dependencies["SectorRotationService"](
                dependencies["SQLiteIndustryIndexSectorRotationProvider"](config.db_file), cadence=cadence
            ),
        )

    def build_portfolio_alert_service() -> Any:
        chip_summary_provider = optional_service(
            "PortfolioChipService",
            lambda: dependencies["PortfolioChipService"](
                config, broker_flow_service=broker_flow_service
            ),
        )
        return dependencies["PortfolioAlertService"](
            portfolio_service=portfolio_service,
            condition_monitor=dependencies["PortfolioConditionMonitor"](),
            chip_summary_provider=chip_summary_provider,
        )

    portfolio_alert_service = optional_service(
        "PortfolioAlertService", build_portfolio_alert_service
    )
    watchlist_trigger_service = optional_service(
        "WatchlistTriggerService",
        lambda: dependencies["WatchlistTriggerService"](
            watchlist_provider=dependencies["WatchlistServiceWatchlistProvider"](
                watchlist_service
            ),
            ranking_provider=dependencies["SQLiteRankingProvider"](config.db_file),
            cadence=cadence,
        ),
    )
    relative_strength_liquidity_service = optional_service(
        "RelativeStrengthLiquidityService",
        lambda: dependencies["RelativeStrengthLiquidityService"](
            provider=dependencies["SQLiteDailyPriceRelativeStrengthLiquidityProvider"](
                config.db_file, market_frame_loader=market_frame_loader
            ),
            cadence=cadence,
        ),
    )
    market_data_visibility_service = optional_service(
        "MarketDataVisibilityService",
        lambda: dependencies["MarketDataVisibilityService"](config.db_file),
    )
    builder = dependencies["DecisionDeskSnapshotBuilder"](
        provider=provider,
        cadence=cadence,
        market_breadth_service=market_breadth_service,
        sector_rotation_service=sector_rotation_service,
        relative_strength_liquidity_service=relative_strength_liquidity_service,
        watchlist_trigger_service=watchlist_trigger_service,
        portfolio_alert_service=portfolio_alert_service,
        smart_money_service=smart_money_service,
        market_frame_loader=market_frame_loader,
        market_data_visibility_service=market_data_visibility_service,
    )
    return DecisionDeskComposition(builder=builder, market_frame_loader=market_frame_loader)


def _configured_pit_reader(config: Any) -> PITSectorMembershipReader | None:
    """只在 config 明確指定 artifact path 時組合 PIT reader。"""

    configured = getattr(config, "pit_sector_membership_paths", None)
    if configured is None:
        configured = getattr(config, "pit_sector_membership_path", None)
    if not configured:
        return None
    return PITSectorMembershipReader.from_config(config)
