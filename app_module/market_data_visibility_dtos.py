"""市場資料可見性的唯讀 DTO 契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceVisibilityStatus:
    source_id: str
    display_name: str
    as_of_date: str
    latest_observation_date: str | None
    available_date: str | None
    row_count: int
    stock_count: int
    quality: str
    pit_status: str
    eligibility: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "as_of_date": self.as_of_date,
            "latest_observation_date": self.latest_observation_date,
            "available_date": self.available_date,
            "row_count": self.row_count,
            "stock_count": self.stock_count,
            "quality": self.quality,
            "pit_status": self.pit_status,
            "eligibility": self.eligibility,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MonthlyRevenueBreadthSummary:
    latest_period: str | None
    stock_count: int
    mom_comparable_count: int
    mom_positive_count: int
    mom_positive_ratio_bp: int | None
    yoy_comparable_count: int
    yoy_positive_count: int
    yoy_positive_ratio_bp: int | None
    quality: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest_period": self.latest_period,
            "stock_count": self.stock_count,
            "mom_comparable_count": self.mom_comparable_count,
            "mom_positive_count": self.mom_positive_count,
            "mom_positive_ratio_bp": self.mom_positive_ratio_bp,
            "yoy_comparable_count": self.yoy_comparable_count,
            "yoy_positive_count": self.yoy_positive_count,
            "yoy_positive_ratio_bp": self.yoy_positive_ratio_bp,
            "quality": self.quality,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class InstitutionalFlowMarketSummary:
    latest_date: str | None
    stock_count: int
    foreign_net_shares: int | None
    investment_trust_net_shares: int | None
    dealer_net_shares: int | None
    quality: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest_date": self.latest_date,
            "stock_count": self.stock_count,
            "foreign_net_shares": self.foreign_net_shares,
            "investment_trust_net_shares": self.investment_trust_net_shares,
            "dealer_net_shares": self.dealer_net_shares,
            "quality": self.quality,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class VisibilityCategoryCount:
    """SQL 聚合後的維度計數；None 表示資料列缺少該維度值。"""

    value: str | None
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "row_count": self.row_count}


@dataclass(frozen=True)
class CurrentFundamentalObservationsSummary:
    """現況基本面觀測的唯讀品質投影，不代表 PIT 或來源接受。"""

    as_of_date: str
    state: str
    row_count: int | None
    stock_count: int | None
    market_counts: tuple[VisibilityCategoryCount, ...] = ()
    kind_counts: tuple[VisibilityCategoryCount, ...] = ()
    source_counts: tuple[VisibilityCategoryCount, ...] = ()
    source_version_counts: tuple[VisibilityCategoryCount, ...] = ()
    period_basis_counts: tuple[VisibilityCategoryCount, ...] = ()
    basis_verified_count: int | None = None
    basis_unverified_count: int | None = None
    basis_unknown_count: int | None = None
    aggregate_feature_eligible_count: int | None = None
    aggregate_feature_ineligible_count: int | None = None
    aggregate_feature_eligibility_unknown_count: int | None = None
    source_available_at_known_count: int | None = None
    source_available_at_missing_count: int | None = None
    source_available_at_after_as_of_date_count: int | None = None
    latest_as_of_date: str | None = None
    latest_observed_at: str | None = None
    latest_source_available_at: str | None = None
    eligibility: str = "research_only"
    pit_status: str = "historical_pit_unverified"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "state": self.state,
            "row_count": self.row_count,
            "stock_count": self.stock_count,
            "market_counts": [item.to_dict() for item in self.market_counts],
            "kind_counts": [item.to_dict() for item in self.kind_counts],
            "source_counts": [item.to_dict() for item in self.source_counts],
            "source_version_counts": [
                item.to_dict() for item in self.source_version_counts
            ],
            "period_basis_counts": [
                item.to_dict() for item in self.period_basis_counts
            ],
            "basis_verified_count": self.basis_verified_count,
            "basis_unverified_count": self.basis_unverified_count,
            "basis_unknown_count": self.basis_unknown_count,
            "aggregate_feature_eligible_count": self.aggregate_feature_eligible_count,
            "aggregate_feature_ineligible_count": self.aggregate_feature_ineligible_count,
            "aggregate_feature_eligibility_unknown_count": (
                self.aggregate_feature_eligibility_unknown_count
            ),
            "source_available_at_known_count": self.source_available_at_known_count,
            "source_available_at_missing_count": self.source_available_at_missing_count,
            "source_available_at_after_as_of_date_count": (
                self.source_available_at_after_as_of_date_count
            ),
            "latest_as_of_date": self.latest_as_of_date,
            "latest_observed_at": self.latest_observed_at,
            "latest_source_available_at": self.latest_source_available_at,
            "eligibility": self.eligibility,
            "pit_status": self.pit_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MarketDataVisibilitySummary:
    as_of_date: str
    monthly_revenue: MonthlyRevenueBreadthSummary
    institutional_flow: InstitutionalFlowMarketSummary
    source_statuses: tuple[SourceVisibilityStatus, ...]
    overall_quality: str
    warnings: tuple[str, ...] = ()
    current_fundamental_observations: CurrentFundamentalObservationsSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "monthly_revenue": self.monthly_revenue.to_dict(),
            "institutional_flow": self.institutional_flow.to_dict(),
            "source_statuses": [status.to_dict() for status in self.source_statuses],
            "overall_quality": self.overall_quality,
            "warnings": list(self.warnings),
            "current_fundamental_observations": (
                self.current_fundamental_observations.to_dict()
                if self.current_fundamental_observations is not None
                else None
            ),
        }
