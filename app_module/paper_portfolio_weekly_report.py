"""Cost-basis aware weekly read model for research paper portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app_module.paper_equal_weight_benchmark_ledger import EqualWeightBenchmarkEntry
from app_module.paper_portfolio_snapshot_repository import PaperPortfolioSnapshot


PAPER_WEEKLY_SNAPSHOT_BASIS_CONTRACT = "paper-weekly-snapshot-cost-basis.v1"
PAPER_WEEKLY_COST_WINDOW_CONTRACT = "[period_start, period_end)"
SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST = "gross_before_fill_cost"
SNAPSHOT_BASIS_NET_AFTER_FILL_COST = "net_after_fill_cost"
_SUPPORTED_SNAPSHOT_BASES = {
    SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST,
    SNAPSHOT_BASIS_NET_AFTER_FILL_COST,
}


@dataclass(frozen=True)
class PaperTradeCostRecord:
    decision_date: str
    total_cost: Decimal
    turnover_bp: int

    def __post_init__(self) -> None:
        if not isinstance(self.total_cost, Decimal) or self.total_cost < 0:
            raise ValueError("total_cost must be a non-negative Decimal")
        if isinstance(self.turnover_bp, bool) or not isinstance(self.turnover_bp, int) or self.turnover_bp < 0:
            raise ValueError("turnover_bp must be a non-negative integer")


@dataclass(frozen=True)
class PaperPortfolioWeeklyReport:
    period_start: str
    period_end: str
    observed_trading_days: int
    gross_return_bp: int
    net_return_bp: int
    benchmark_return_bp: int
    net_excess_return_bp: int
    total_cost: Decimal
    turnover_bp: int
    data_quality: str
    warnings: tuple[str, ...]
    snapshot_basis_contract: str = PAPER_WEEKLY_SNAPSHOT_BASIS_CONTRACT
    snapshot_basis: str = SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST
    cost_window_contract: str = PAPER_WEEKLY_COST_WINDOW_CONTRACT
    cost_window_coverage_proven: bool = True
    gross_return_method: str = "snapshot_value_before_fill_cost"
    research_only: bool = True
    investment_effectiveness_claim: bool = False


class PaperPortfolioWeeklyReportService:
    def build(
        self,
        *,
        portfolio_snapshots: Iterable[PaperPortfolioSnapshot],
        benchmark_entries: Iterable[EqualWeightBenchmarkEntry],
        trade_costs: Iterable[PaperTradeCostRecord],
        expected_trading_days: int,
        snapshot_basis: str = SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST,
        cost_window_coverage_proven: bool = True,
    ) -> PaperPortfolioWeeklyReport:
        """建立週報 read model。

        為維持既有純 API 相容性，未指定 ``snapshot_basis`` 時仍將 snapshots
        視為 gross-before-fill-cost。此預設只適用已確認為 gross NAV 的舊呼叫端；
        新呼叫端必須明確傳入 basis 與成本視窗覆蓋證明。net NAV 不得沿用此預設，
        也不可再扣一次成本。
        """

        snapshots = tuple(sorted(portfolio_snapshots, key=lambda item: item.decision_date))
        benchmarks = tuple(sorted(benchmark_entries, key=lambda item: item.decision_date))
        if len(snapshots) < 2 or len(benchmarks) < 2:
            raise ValueError("weekly report requires at least two portfolio and benchmark observations")
        if expected_trading_days <= 0:
            raise ValueError("expected_trading_days must be positive")
        if snapshot_basis not in _SUPPORTED_SNAPSHOT_BASES:
            raise ValueError("snapshot_basis is unsupported")
        if type(cost_window_coverage_proven) is not bool:
            raise ValueError("cost_window_coverage_proven must be bool")
        if not cost_window_coverage_proven:
            raise ValueError("weekly report requires proven [S,D) cost-window coverage")
        if (snapshots[0].decision_date, snapshots[-1].decision_date) != (
            benchmarks[0].decision_date,
            benchmarks[-1].decision_date,
        ):
            raise ValueError("portfolio and benchmark require aligned boundary dates")
        period_start = snapshots[0].decision_date
        period_end = snapshots[-1].decision_date
        costs = tuple(
            item
            for item in trade_costs
            if _in_preopen_cost_window(item.decision_date, period_start, period_end)
        )
        total_cost = sum((item.total_cost for item in costs), Decimal("0")).quantize(
            Decimal("0.01")
        )
        start_value = snapshots[0].total_value
        end_value = snapshots[-1].total_value
        warnings: tuple[str, ...]
        if snapshot_basis == SNAPSHOT_BASIS_GROSS_BEFORE_FILL_COST:
            gross = _return_bp(start_value, end_value)
            net = _return_bp(start_value, end_value - total_cost)
            gross_return_method = "snapshot_value_before_fill_cost"
            warnings = ()
        else:
            # net NAV 已含成交成本，不可再扣 total_cost。
            net = _return_bp(start_value, end_value)
            gross = _return_bp(start_value, end_value + total_cost)
            gross_return_method = "net_nav_plus_verified_period_cost_addback"
            warnings = ("gross_cost_addback_is_not_counterfactual",)
        benchmark = _return_bp(benchmarks[0].total_value, benchmarks[-1].total_value)
        observed_days = len({item.decision_date for item in snapshots})
        if observed_days < expected_trading_days:
            warnings = (*warnings, "incomplete_trading_week")
        return PaperPortfolioWeeklyReport(
            period_start=snapshots[0].decision_date,
            period_end=snapshots[-1].decision_date,
            observed_trading_days=observed_days,
            gross_return_bp=gross,
            net_return_bp=net,
            benchmark_return_bp=benchmark,
            net_excess_return_bp=net - benchmark,
            total_cost=total_cost,
            turnover_bp=sum(item.turnover_bp for item in costs),
            data_quality="OBSERVED" if not warnings else "DEGRADED",
            warnings=warnings,
            snapshot_basis=snapshot_basis,
            cost_window_coverage_proven=cost_window_coverage_proven,
            gross_return_method=gross_return_method,
        )


def _in_preopen_cost_window(event_date: str, period_start: str, period_end: str) -> bool:
    """判斷成交日期是否位於起始日含、結束日不含的成本視窗。"""

    return period_start <= event_date < period_end


def _return_bp(start: Decimal, end: Decimal) -> int:
    if start <= 0:
        raise ValueError("return denominator must be positive")
    return int((end - start) * 10000 / start)
