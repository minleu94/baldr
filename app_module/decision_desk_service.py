from __future__ import annotations

import inspect
from datetime import date, datetime
from typing import Any, Callable, Protocol, TypeVar
from dataclasses import replace
from copy import deepcopy
from pathlib import Path

from app_module.exceptions import BacktestCancelledError
from app_module.market_session_cadence import MarketSessionCadence
from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskSnapshot,
    MarketBreadthSummary,
    MarketRegimeSummary,
    PortfolioAlertSummary,
    SectorRotationSummary,
    WatchlistTriggerSummary,
    RelativeStrengthLiquiditySummary,
    DecisionDeskRiskPromptSummary,
    RecommendationDeskSummary,
)
from app_module.recommendation.legacy_dtos import RecommendationResultDTO
from app_module.recommendation.contracts import QualityStatus, RecommendationExecution
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    execution_result_config,
    recommendation_runs_dir,
    select_latest_saved_recommendation,
)
from app_module.decision_desk_snapshot_support import compute_overall_quality, collect_snapshot_warnings, collect_smart_money_candidate_codes
from app_module.decision_desk_dashboard_service import DecisionDeskDashboardComposer
from app_module.decision_desk_risk_prompt_service import DecisionDeskRiskPromptService
from app_module.market_data_visibility_dtos import (
    InstitutionalFlowMarketSummary,
    MarketDataVisibilitySummary,
    MonthlyRevenueBreadthSummary,
    SourceVisibilityStatus,
)


class DailyDecisionDeskProvider(Protocol):
    def fetch_market_regime(self, as_of_date: date) -> MarketRegimeSummary | None: ...

    def fetch_market_breadth(self, as_of_date: date) -> MarketBreadthSummary | None: ...

    def fetch_sector_rotation(self, as_of_date: date) -> SectorRotationSummary | None: ...

    def fetch_watchlist_triggers(self, as_of_date: date) -> WatchlistTriggerSummary | None: ...

    def fetch_portfolio_alerts(self, as_of_date: date) -> PortfolioAlertSummary | None: ...


class MarketBreadthSectionService(Protocol):
    def build_snapshot(self, as_of_date: date) -> MarketBreadthSummary: ...


class SectorRotationSectionService(Protocol):
    def build_snapshot(self, as_of_date: date) -> SectorRotationSummary: ...


class WatchlistTriggerSectionService(Protocol):
    def build_snapshot(self, as_of_date: date) -> WatchlistTriggerSummary: ...


class PortfolioAlertSectionService(Protocol):
    def build_snapshot(self, as_of_date: date) -> PortfolioAlertSummary: ...


class RelativeStrengthLiquiditySectionService(Protocol):
    def build_snapshot(self, as_of_date: date) -> RelativeStrengthLiquiditySummary: ...


class SmartMoneyDashboardService(Protocol):
    def build_dashboard_summary(self, decision_date: date, stock_codes: tuple[str, ...] = ()): ...


def _raise_if_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise BacktestCancelledError("決策台摘要載入已取消。")


def _call_with_optional_cancel_callback(method, *args, cancel_callback, **kwargs):
    if cancel_callback is None:
        return method(*args, **kwargs)

    supports_callback = False
    try:
        parameters = inspect.signature(method).parameters.values()
        supports_callback = any(
            parameter.name == "cancel_callback"
            and parameter.kind is not inspect.Parameter.POSITIONAL_ONLY
            for parameter in parameters
        ) or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    except (TypeError, ValueError):
        pass

    _raise_if_cancelled(cancel_callback)
    if supports_callback:
        result = method(*args, **kwargs, cancel_callback=cancel_callback)
        _raise_if_cancelled(cancel_callback)
        return result
    result = method(*args, **kwargs)
    _raise_if_cancelled(cancel_callback)
    return result


class DecisionMarketFrameResetter(Protocol):
    def reset(self, as_of_date: date) -> None: ...


class MarketDataVisibilitySectionService(Protocol):
    def build_summary(self, *, as_of_date: date) -> MarketDataVisibilitySummary: ...


class SavedRecommendationDeskProvider:
    """讀取已保存推薦，不初始化 writer，不重新評分。"""

    def __init__(self, config: Any, *, queries: Any | None = None):
        self.runs_dir = recommendation_runs_dir(config)
        self.queries = queries or build_recommendation_execution_queries(config)

    def fetch(self, as_of_date: date):
        candidates: list[
            tuple[str, RecommendationExecutionReadModel, RecommendationDeskSummary]
        ] = []
        for read_model in self.queries.list():
            summary = self._summary(read_model, as_of_date)
            if summary is not None and summary.as_of_date is not None:
                candidates.append(
                    (
                        summary.as_of_date.isoformat(),
                        read_model,
                        summary,
                    )
                )
        if not candidates:
            return None
        latest_as_of_date = max(item[0] for item in candidates)
        same_day = tuple(item for item in candidates if item[0] == latest_as_of_date)
        latest, diagnostic = select_latest_saved_recommendation(
            tuple(item[1] for item in same_day)
        )
        if diagnostic or latest is None:
            return None
        return next(summary for _day, model, summary in same_day if model is latest)

    def _summary(
        self,
        read_model: RecommendationExecutionReadModel,
        requested_date: date,
    ) -> RecommendationDeskSummary | None:
        legacy = read_model.legacy_result
        if legacy is not None:
            context = deepcopy(legacy.run_context)
            cutoff_text = str(context.get("as_of_date") or "")
            if not cutoff_text:
                return None
            cutoff = date.fromisoformat(cutoff_text)
            if cutoff > requested_date:
                return None
            warnings = tuple(str(item) for item in context.get("warnings", [])) + tuple(
                legacy.exclusion_warnings_json
            )
            quality = DecisionDeskQuality.OBSERVED
            if cutoff < requested_date:
                warnings += (f"recommendation_as_of_fallback:{cutoff.isoformat()}",)
                quality = DecisionDeskQuality.DEGRADED
            if legacy.exclusion_quality in {"missing", "degraded"}:
                quality = DecisionDeskQuality.DEGRADED
            return RecommendationDeskSummary(
                cutoff,
                quality,
                warnings,
                legacy.result_id,
                tuple(item.stock_code for item in legacy.recommendations),
                str(context.get("profile_id") or legacy.config.get("profile_id") or ""),
                context,
            )

        execution = read_model.execution
        if execution is None or execution.decision is None:
            return None
        canonical_cutoff = execution.context.as_of_date
        if canonical_cutoff is None or canonical_cutoff > requested_date:
            return None
        config = execution_result_config(execution)
        profile_id = str(
            config.get("profile_id")
            or (
                execution.context.profile_ref.reference_id
                if execution.context.profile_ref is not None
                else ""
            )
        )
        warnings = tuple(execution.context.warnings) + tuple(execution.quality.warnings)
        quality = {
            QualityStatus.COMPLETE: DecisionDeskQuality.OBSERVED,
            QualityStatus.DEGRADED: DecisionDeskQuality.DEGRADED,
            QualityStatus.UNKNOWN: DecisionDeskQuality.MISSING,
            QualityStatus.UNAVAILABLE: DecisionDeskQuality.MISSING,
        }[execution.quality.status]
        canonical_context: dict[str, Any] = {
            "as_of_date": canonical_cutoff.isoformat(),
            "warnings": list(warnings),
        }
        if profile_id:
            canonical_context["profile_id"] = profile_id
        if execution.context.created_at is not None:
            canonical_context["created_at"] = execution.context.created_at.isoformat()
        source_ids = tuple(dict.fromkeys(item.source_id for item in execution.context.source_refs))
        if len(source_ids) == 1:
            canonical_context["source_id"] = source_ids[0]
        return RecommendationDeskSummary(
            canonical_cutoff,
            quality,
            warnings,
            execution.result_id,
            tuple(item.stock_code for item in execution.decision.items),
            profile_id,
            canonical_context,
        )

class PortfolioLedgerDeskProvider:
    """消費已注入的候選 ledger App 服務；不初始化 repository 或計算風控。"""

    def __init__(self, service: Any, *, portfolio_id: str = "default", source_namespace: str = "manual"):
        self.service = service
        self.portfolio_id = portfolio_id
        self.source_namespace = source_namespace

    def fetch(self, as_of_date: date):
        return self.service.build_ledger_read_model(
            portfolio_id=self.portfolio_id, source_namespace=self.source_namespace,
            as_of_date=as_of_date.isoformat(),
        )


Section = TypeVar("Section", MarketRegimeSummary, MarketBreadthSummary, SectorRotationSummary,
                  RelativeStrengthLiquiditySummary, WatchlistTriggerSummary, PortfolioAlertSummary)



class DecisionDeskSnapshotBuilder:
    """Builder for Daily Decision Desk snapshot."""

    def __init__(
        self,
        provider: DailyDecisionDeskProvider | None = None,
        *,
        schema_version: int = 2,
        cadence: MarketSessionCadence | None = None,
        clock: Callable[[], datetime] | None = None,
        market_breadth_service: MarketBreadthSectionService | None = None,
        sector_rotation_service: SectorRotationSectionService | None = None,
        relative_strength_liquidity_service: RelativeStrengthLiquiditySectionService | None = None,
        watchlist_trigger_service: WatchlistTriggerSectionService | None = None,
        portfolio_alert_service: PortfolioAlertSectionService | None = None,
        risk_prompt_service: DecisionDeskRiskPromptService | None = None,
        dashboard_composer: DecisionDeskDashboardComposer | None = None,
        smart_money_service: SmartMoneyDashboardService | None = None,
        market_frame_loader: DecisionMarketFrameResetter | None = None,
        market_data_visibility_service: MarketDataVisibilitySectionService | None = None,
        recommendation_provider: Any | None = None,
        portfolio_ledger_provider: Any | None = None,
    ):
        self.provider = provider
        self.cadence = cadence
        self.schema_version = schema_version
        self.clock = clock or datetime.now
        self.market_breadth_service = market_breadth_service
        self.sector_rotation_service = sector_rotation_service
        self.relative_strength_liquidity_service = relative_strength_liquidity_service
        self.watchlist_trigger_service = watchlist_trigger_service
        self.portfolio_alert_service = portfolio_alert_service
        self.risk_prompt_service = risk_prompt_service or DecisionDeskRiskPromptService()
        self.dashboard_composer = dashboard_composer or DecisionDeskDashboardComposer()
        self.smart_money_service = smart_money_service
        self.market_frame_loader = market_frame_loader
        self.market_data_visibility_service = market_data_visibility_service
        self.recommendation_provider = recommendation_provider
        self.portfolio_ledger_provider = portfolio_ledger_provider

    def build_snapshot(
        self,
        as_of_date: date,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DecisionDeskSnapshot:
        _raise_if_cancelled(cancel_callback)
        if self.market_frame_loader is not None:
            self.market_frame_loader.reset(as_of_date)
        _raise_if_cancelled(cancel_callback)
        market_regime = self._build_market_regime(as_of_date)
        _raise_if_cancelled(cancel_callback)
        market_breadth = self._build_market_breadth(
            as_of_date,
            cancel_callback=cancel_callback,
        )
        _raise_if_cancelled(cancel_callback)
        sector_rotation = self._build_sector_rotation(as_of_date)
        _raise_if_cancelled(cancel_callback)
        relative_strength_liquidity = self._build_relative_strength_liquidity(
            as_of_date,
            cancel_callback=cancel_callback,
        )
        _raise_if_cancelled(cancel_callback)
        watchlist_triggers = self._build_watchlist_triggers(as_of_date)
        _raise_if_cancelled(cancel_callback)
        portfolio_alerts = self._build_portfolio_alerts(as_of_date)
        _raise_if_cancelled(cancel_callback)
        market_regime = self._dated_section(market_regime, as_of_date, "market_regime")
        market_breadth = self._dated_section(market_breadth, as_of_date, "market_breadth")
        sector_rotation = self._dated_section(sector_rotation, as_of_date, "sector_rotation")
        relative_strength_liquidity = self._dated_section(relative_strength_liquidity, as_of_date, "relative_strength_liquidity")
        watchlist_triggers = self._dated_section(watchlist_triggers, as_of_date, "watchlist_triggers")
        portfolio_alerts = self._dated_section(portfolio_alerts, as_of_date, "portfolio_alerts")
        ledger_lineage = self._build_ledger_lineage(as_of_date) if self.portfolio_ledger_provider is not None else None
        _raise_if_cancelled(cancel_callback)
        if ledger_lineage is not None and ledger_lineage.get("quality") != "complete":
            blocked = ledger_lineage.get("quality") == "blocked"
            portfolio_alerts = replace(
                portfolio_alerts,
                quality=DecisionDeskQuality.MISSING if blocked else DecisionDeskQuality.DEGRADED,
                warnings=portfolio_alerts.warnings + tuple(ledger_lineage.get("warnings", ()))
                + tuple(f"portfolio_ledger_missing:{item}" for item in ledger_lineage.get("missing_inputs", ())),
                alert_level=None if blocked else portfolio_alerts.alert_level,
                alert_count=None if blocked else portfolio_alerts.alert_count,
                alert_codes=() if blocked else portfolio_alerts.alert_codes,
                attributions=() if blocked else portfolio_alerts.attributions,
            )
        recommendations = self._build_recommendations(as_of_date) if self.recommendation_provider is not None else None
        _raise_if_cancelled(cancel_callback)
        market_data_visibility = self._build_market_data_visibility(as_of_date)
        _raise_if_cancelled(cancel_callback)
        risk_prompts = self.risk_prompt_service.build_summary(
            as_of_date=as_of_date,
            market_regime=market_regime,
            market_breadth=market_breadth,
            sector_rotation=sector_rotation,
            relative_strength_liquidity=relative_strength_liquidity,
            watchlist_triggers=watchlist_triggers,
            portfolio_alerts=portfolio_alerts,
        )
        sections = (
            market_regime,
            market_breadth,
            sector_rotation,
            relative_strength_liquidity,
            watchlist_triggers,
            portfolio_alerts,
            risk_prompts,
        )
        generated_at = self.clock()
        overall_quality = self._compute_overall_quality(sections)
        warnings = self._collect_snapshot_warnings(sections)
        if recommendations is not None:
            warnings += recommendations.warnings
            if overall_quality != DecisionDeskQuality.MISSING and recommendations.quality in {DecisionDeskQuality.MISSING, DecisionDeskQuality.DEGRADED}:
                overall_quality = DecisionDeskQuality.DEGRADED
        lineage_sections: tuple[MarketRegimeSummary | MarketBreadthSummary | SectorRotationSummary | RelativeStrengthLiquiditySummary | WatchlistTriggerSummary | PortfolioAlertSummary | DecisionDeskRiskPromptSummary, ...] = sections
        source_lineage = {name: {"as_of_date": section.as_of_date.isoformat() if section.as_of_date else None,
                                  "quality": section.quality.value, "warnings": list(section.warnings),
                                  "metadata": deepcopy(getattr(section, "meta", None) or {})}
                          for name, section in zip(("market_regime", "market_breadth", "sector_rotation", "relative_strength_liquidity", "watchlist_triggers", "portfolio_alerts", "risk_prompts"), lineage_sections)}
        if recommendations is not None:
            source_lineage["recommendations"] = recommendations.to_dict()
        if ledger_lineage is not None:
            source_lineage["portfolio_ledger"] = ledger_lineage
        smart_money_summary = None
        if self.smart_money_service is not None:
            try:
                smart_money_summary = _call_with_optional_cancel_callback(
                    self.smart_money_service.build_dashboard_summary,
                    as_of_date,
                    cancel_callback=cancel_callback,
                    stock_codes=self._collect_smart_money_candidate_codes(
                        relative_strength_liquidity,
                        watchlist_triggers,
                        portfolio_alerts,
                    ),
                )
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                warnings = tuple(warnings) + (f"smart_money_dashboard_error:{exc}",)
                overall_quality = DecisionDeskQuality.DEGRADED
        _raise_if_cancelled(cancel_callback)
        action_summary = None
        sector_focus = None
        stock_focus = None
        try:
            _raise_if_cancelled(cancel_callback)
            dashboard = self.dashboard_composer.compose(
                market_regime=market_regime,
                market_breadth=market_breadth,
                sector_rotation=sector_rotation,
                relative_strength_liquidity=relative_strength_liquidity,
                watchlist_triggers=watchlist_triggers,
                portfolio_alerts=portfolio_alerts,
                smart_money_summary=smart_money_summary,
            )
            action_summary = dashboard.action_summary
            sector_focus = dashboard.sector_focus
            stock_focus = dashboard.stock_focus
            _raise_if_cancelled(cancel_callback)
        except BacktestCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            warnings = tuple(warnings) + (f"dashboard_composer_error:{exc}",)
            overall_quality = DecisionDeskQuality.DEGRADED

        return DecisionDeskSnapshot(
            as_of_date=as_of_date,
            generated_at=generated_at,
            schema_version=self.schema_version,
            overall_quality=overall_quality,
            warnings=warnings,
            market_regime=market_regime,
            market_breadth=market_breadth,
            sector_rotation=sector_rotation,
            relative_strength_liquidity=relative_strength_liquidity,
            watchlist_triggers=watchlist_triggers,
            portfolio_alerts=portfolio_alerts,
            risk_prompts=risk_prompts,
            action_summary=action_summary,
            sector_focus=sector_focus,
            stock_focus=stock_focus,
            market_data_visibility=market_data_visibility,
            recommendations=recommendations,
            source_lineage=source_lineage,
        )

    def _build_ledger_lineage(self, as_of_date: date) -> dict[str, Any]:
        try:
            if self.portfolio_ledger_provider is None:
                raise ValueError("provider_missing")
            model = self.portfolio_ledger_provider.fetch(as_of_date)
            payload = model.to_dict()
            if date.fromisoformat(str(payload["as_of_date"])) > as_of_date:
                raise ValueError("future_source_rejected")
            if payload["quality"] not in {"complete", "degraded", "blocked"}:
                raise ValueError("unknown_quality")
            if payload["as_of_date"] != as_of_date.isoformat():
                payload["quality"] = "degraded" if payload["quality"] != "blocked" else "blocked"
                payload["warnings"] = list(payload.get("warnings", ())) + ["portfolio_ledger_date_fallback"]
            return deepcopy(payload)
        except BacktestCancelledError:
            raise
        except Exception as exc:
            return {"as_of_date": None, "quality": "blocked", "missing_inputs": ["ledger_read_model"],
                    "warnings": [f"portfolio_ledger_error:{type(exc).__name__}:{exc}"], "candidate_only": True}

    def _dated_section(self, section: Section, as_of_date: date, name: str) -> Section:
        if section.as_of_date is None or section.as_of_date > as_of_date:
            return type(section)(as_of_date=None, quality=DecisionDeskQuality.MISSING,
                                 warnings=tuple(section.warnings) + (f"{name}_date_unavailable_or_future",))
        if section.as_of_date < as_of_date:
            if (self.cadence is not None and name in {
                    "market_breadth", "sector_rotation", "relative_strength_liquidity", "watchlist_triggers"}
                    and self.cadence.assess(as_of_date, section.as_of_date).current):
                return section
            quality = DecisionDeskQuality.MISSING if section.quality == DecisionDeskQuality.MISSING else DecisionDeskQuality.DEGRADED
            return replace(section, quality=quality, warnings=tuple(section.warnings) + (f"{name}_as_of_fallback:{section.as_of_date.isoformat()}",))
        return section

    def _build_recommendations(self, as_of_date: date) -> RecommendationDeskSummary:
        try:
            if self.recommendation_provider is None:
                return RecommendationDeskSummary(None, DecisionDeskQuality.MISSING, ("recommendation_snapshot_missing",))
            result = self.recommendation_provider.fetch(as_of_date)
            if result is None:
                return RecommendationDeskSummary(None, DecisionDeskQuality.MISSING, ("recommendation_snapshot_missing",))
            if isinstance(result, RecommendationDeskSummary):
                return result
            context = deepcopy(result.run_context)
            cutoff = date.fromisoformat(str(context["as_of_date"]))
            if cutoff > as_of_date:
                raise ValueError("recommendation_future_date")
            warnings = tuple(str(item) for item in context.get("warnings", [])) + tuple(result.exclusion_warnings_json)
            quality = DecisionDeskQuality.OBSERVED
            if cutoff < as_of_date:
                warnings += (f"recommendation_as_of_fallback:{cutoff.isoformat()}",)
                quality = DecisionDeskQuality.DEGRADED
            if result.exclusion_quality in {"missing", "degraded"}:
                quality = DecisionDeskQuality.DEGRADED
            return RecommendationDeskSummary(cutoff, quality, warnings, result.result_id,
                                             tuple(item.stock_code for item in result.recommendations),
                                             str(context.get("profile_id") or result.config.get("profile_id") or ""), context)
        except BacktestCancelledError:
            raise
        except Exception as exc:
            return RecommendationDeskSummary(None, DecisionDeskQuality.MISSING, (f"recommendation_snapshot_error:{exc}",))

    def _build_market_data_visibility(
        self, as_of_date: date
    ) -> MarketDataVisibilitySummary | None:
        if self.market_data_visibility_service is None:
            return None
        try:
            return self.market_data_visibility_service.build_summary(as_of_date=as_of_date)
        except BacktestCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            warning = f"market_data_visibility_error:{exc}"
            source_names = (
                ("fundamental_monthly_revenues", "月營收"),
                ("institutional_flows", "三大法人"),
                ("credit_transactions", "信用交易"),
                ("tdcc_shareholding", "集保股權分散"),
                ("broker_flows", "券商分點"),
            )
            statuses = tuple(
                SourceVisibilityStatus(
                    source_id=source_id,
                    display_name=display_name,
                    as_of_date=as_of_date.isoformat(),
                    latest_observation_date=None,
                    available_date=None,
                    row_count=0,
                    stock_count=0,
                    quality="MISSING",
                    pit_status="missing",
                    eligibility="none",
                    warnings=(warning,),
                )
                for source_id, display_name in source_names
            )
            return MarketDataVisibilitySummary(
                as_of_date=as_of_date.isoformat(),
                monthly_revenue=MonthlyRevenueBreadthSummary(
                    latest_period=None,
                    stock_count=0,
                    mom_comparable_count=0,
                    mom_positive_count=0,
                    mom_positive_ratio_bp=None,
                    yoy_comparable_count=0,
                    yoy_positive_count=0,
                    yoy_positive_ratio_bp=None,
                    quality="MISSING",
                    warnings=(warning,),
                ),
                institutional_flow=InstitutionalFlowMarketSummary(
                    latest_date=None,
                    stock_count=0,
                    foreign_net_shares=None,
                    investment_trust_net_shares=None,
                    dealer_net_shares=None,
                    quality="MISSING",
                    warnings=(warning,),
                ),
                source_statuses=statuses,
                overall_quality="DEGRADED",
                warnings=(warning,),
            )

    def _build_market_regime(self, as_of_date: date) -> MarketRegimeSummary:
        if self.provider is None:
            return MarketRegimeSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_regime_missing",),
                regime_label=None,
            )
        try:
            regime_service = getattr(self.provider, "regime_service", None)
            dto_method = getattr(regime_service, "detect_regime_dto", None)
            if callable(dto_method):
                dto = dto_method(as_of_date=as_of_date.isoformat())
                return MarketRegimeSummary(dto.effective_date, DecisionDeskQuality(dto.quality), tuple(dto.warnings),
                                           regime_label=dto.regime_name_cn or dto.regime,
                                           regime_confidence=dto.match_score_bp,
                                           meta={**dict(dto.details or {}), "source_id": dto.source_id, "source_version": dto.source_version})
            snapshot = self.provider.fetch_market_regime(as_of_date)
        except BacktestCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            return MarketRegimeSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=(f"market_regime_fetch_error:{exc}",),
                regime_label=None,
            )
        if snapshot is None:
            return MarketRegimeSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_regime_missing",),
                regime_label=None,
            )
        return snapshot

    def _build_market_breadth(
        self,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MarketBreadthSummary:
        snapshot: MarketBreadthSummary | None
        if self.market_breadth_service is not None:
            try:
                snapshot = _call_with_optional_cancel_callback(
                    self.market_breadth_service.build_snapshot,
                    as_of_date,
                    cancel_callback=cancel_callback,
                )
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return MarketBreadthSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"market_breadth_fetch_error:{exc}",),
                )
        elif self.provider is not None:
            try:
                snapshot = _call_with_optional_cancel_callback(
                    self.provider.fetch_market_breadth,
                    as_of_date,
                    cancel_callback=cancel_callback,
                )
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return MarketBreadthSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"market_breadth_fetch_error:{exc}",),
                )
        else:
            return MarketBreadthSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_breadth_missing",),
            )

        if snapshot is None:
            return MarketBreadthSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_breadth_missing",),
            )
        return snapshot

    def _build_sector_rotation(self, as_of_date: date) -> SectorRotationSummary:
        snapshot: SectorRotationSummary | None
        if self.sector_rotation_service is not None:
            try:
                snapshot = self.sector_rotation_service.build_snapshot(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return SectorRotationSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"sector_rotation_fetch_error:{exc}",),
                )
        elif self.provider is not None:
            try:
                snapshot = self.provider.fetch_sector_rotation(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return SectorRotationSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"sector_rotation_fetch_error:{exc}",),
                )
        else:
            return SectorRotationSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("sector_rotation_missing",),
            )

        if snapshot is None:
            return SectorRotationSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("sector_rotation_missing",),
            )
        return snapshot

    def _build_relative_strength_liquidity(
        self,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> RelativeStrengthLiquiditySummary:
        if self.relative_strength_liquidity_service is not None:
            try:
                snapshot = _call_with_optional_cancel_callback(
                    self.relative_strength_liquidity_service.build_snapshot,
                    as_of_date,
                    cancel_callback=cancel_callback,
                )
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return RelativeStrengthLiquiditySummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"relative_strength_liquidity_fetch_error:{exc}",),
                )
            if snapshot is not None:
                return snapshot

        return RelativeStrengthLiquiditySummary(
            as_of_date=as_of_date,
            quality=DecisionDeskQuality.MISSING,
            warnings=("relative_strength_liquidity_missing",),
        )

    def _build_watchlist_triggers(self, as_of_date: date) -> WatchlistTriggerSummary:
        snapshot: WatchlistTriggerSummary | None
        if self.watchlist_trigger_service is not None:
            try:
                snapshot = self.watchlist_trigger_service.build_snapshot(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return WatchlistTriggerSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"watchlist_triggers_fetch_error:{exc}",),
                    trigger_count=0,
                    triggered_codes=(),
                )
        elif self.provider is not None:
            try:
                snapshot = self.provider.fetch_watchlist_triggers(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return WatchlistTriggerSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"watchlist_triggers_fetch_error:{exc}",),
                    trigger_count=0,
                    triggered_codes=(),
                )
        else:
            return WatchlistTriggerSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("watchlist_triggers_missing",),
                trigger_count=0,
                triggered_codes=(),
            )

        if snapshot is None:
            return WatchlistTriggerSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("watchlist_triggers_missing",),
                trigger_count=0,
                triggered_codes=(),
            )
        return snapshot

    def _build_portfolio_alerts(self, as_of_date: date) -> PortfolioAlertSummary:
        snapshot: PortfolioAlertSummary | None
        if self.portfolio_alert_service is not None:
            try:
                snapshot = self.portfolio_alert_service.build_snapshot(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return PortfolioAlertSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"portfolio_alerts_fetch_error:{exc}",),
                    alert_count=0,
                    alert_codes=(),
                    alert_level=None,
                )
        elif self.provider is not None:
            try:
                snapshot = self.provider.fetch_portfolio_alerts(as_of_date)
            except BacktestCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                return PortfolioAlertSummary(
                    as_of_date=as_of_date,
                    quality=DecisionDeskQuality.DEGRADED,
                    warnings=(f"portfolio_alerts_fetch_error:{exc}",),
                    alert_count=0,
                    alert_codes=(),
                    alert_level=None,
                )
        else:
            return PortfolioAlertSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("portfolio_alerts_missing",),
                alert_count=0,
                alert_codes=(),
                alert_level=None,
            )

        if snapshot is None:
            return PortfolioAlertSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("portfolio_alerts_missing",),
                alert_count=0,
                alert_codes=(),
                alert_level=None,
            )
        return snapshot

    @staticmethod
    def _compute_overall_quality(
        sections: tuple[
            MarketRegimeSummary,
            MarketBreadthSummary,
            SectorRotationSummary,
            RelativeStrengthLiquiditySummary,
            WatchlistTriggerSummary,
            PortfolioAlertSummary,
            DecisionDeskRiskPromptSummary,
        ],
    ) -> DecisionDeskQuality:
        return compute_overall_quality(sections)

    @staticmethod
    def _collect_snapshot_warnings(
        sections: tuple[
            MarketRegimeSummary,
            MarketBreadthSummary,
            SectorRotationSummary,
            RelativeStrengthLiquiditySummary,
            WatchlistTriggerSummary,
            PortfolioAlertSummary,
            DecisionDeskRiskPromptSummary,
        ],
    ) -> tuple[str, ...]:
        return collect_snapshot_warnings(sections)

    @staticmethod
    def _collect_smart_money_candidate_codes(
        relative_strength_liquidity: RelativeStrengthLiquiditySummary,
        watchlist_triggers: WatchlistTriggerSummary,
        portfolio_alerts: PortfolioAlertSummary,
    ) -> tuple[str, ...]:
        return collect_smart_money_candidate_codes(relative_strength_liquidity, watchlist_triggers, portfolio_alerts)
