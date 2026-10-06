"""由明示 Paper route 映射既有檔名；不建立、搬移或補造資料。"""

from dataclasses import dataclass
from pathlib import Path

from app_module.personal_store_routes import (
    PersonalStoreDomain, PersonalStoreRoute, PersonalStoreRouteError,
)


@dataclass(frozen=True)
class PersonalPaperStorePaths:
    state_db: Path
    benchmark_db: Path
    cost_ledger_db: Path
    baseline: Path
    status: Path

    @classmethod
    def from_route(cls, route: PersonalStoreRoute, *, portfolio_id: str) -> "PersonalPaperStorePaths":
        if route.domain is not PersonalStoreDomain.PAPER:
            raise PersonalStoreRouteError("paper_domain_required")
        if not portfolio_id.strip() or route.identity.key != portfolio_id:
            raise PersonalStoreRouteError("paper_identity_mismatch")
        source = route.read_source
        if not source.is_absolute() or ".." in source.parts:
            raise PersonalStoreRouteError("absolute_path_required")
        if source.name != "paper_trade_ledger.sqlite" or source.parent.name != "paper_portfolio":
            raise PersonalStoreRouteError("paper_existing_layout_required")
        root = source.parent.parent
        return cls(
            state_db=source.parent / "paper_portfolio.sqlite",
            benchmark_db=source.parent / "paper_equal_weight_benchmark.sqlite",
            cost_ledger_db=source,
            baseline=source.parent / "baseline_20260712.json",
            status=root / "scheduled" / "paper_portfolio_daily" / "latest_status.json",
        )

    @staticmethod
    def require_selected(override: str | Path | None, selected: Path) -> Path:
        if override is not None and Path(override) != selected:
            raise PersonalStoreRouteError("paper_route_override_mismatch", str(override))
        return selected
