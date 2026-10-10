"""前向、空倉策略 Paper account 開戶 writer 候選。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotReceipt,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountService,
)


class StrategyPaperAccountSeedError(ValueError):
    """策略帳戶 cash seed 缺少已驗證 binding 或前向時鐘時拒絕。"""


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountCashSeed:
    snapshot: PaperPortfolioSnapshot
    receipt: PaperPortfolioSnapshotReceipt


def _utc_now() -> datetime:
    """取得 writer 觀測時鐘；呼叫端不能回填 seed 時間。"""

    return datetime.now(timezone.utc)


class StrategyPaperAccountCashSeedWriter:
    """依明示 exact binding 建立 500000 元現金、空持倉的前向初始 snapshot。"""

    def __init__(
        self,
        *,
        account_service: StrategyPaperAccountService,
        personal_paths: PersonalDataPaths,
    ) -> None:
        self.account_service = account_service
        self.personal_paths = personal_paths

    def create_cash_seed(
        self,
        *,
        strategy_id: str,
        strategy_version_id: str,
        account_namespace: str,
    ) -> StrategyPaperAccountCashSeed:
        selection = self.account_service.select_exact_version(
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            account_namespace=account_namespace,
        )
        if (
            selection.status is not AccountBindingStatus.READY
            or selection.binding is None
            or selection.route is None
        ):
            reason = ",".join(selection.blockers) or "strategy_account_binding_unavailable"
            raise StrategyPaperAccountSeedError(reason)

        binding = selection.binding
        policy = PaperPortfolioPolicyConfig()
        if (
            str(policy.initial_capital) != binding.initial_capital
            or policy.max_positions != binding.max_positions
        ):
            raise StrategyPaperAccountSeedError("strategy_account_seed_policy_mismatch")

        created_at = _utc_now()
        if (
            not isinstance(created_at, datetime)
            or created_at.tzinfo is None
            or created_at.utcoffset() is None
        ):
            raise StrategyPaperAccountSeedError("strategy_account_seed_clock_unknown")
        created_at = created_at.astimezone(timezone.utc)
        created_at_text = created_at.isoformat()
        seed_date = created_at.astimezone(TAIWAN_MARKET_TIMEZONE).date().isoformat()
        if seed_date < binding.start_date:
            raise StrategyPaperAccountSeedError("strategy_account_seed_start_date_in_future")

        source_result_id = (
            "strategy-account-cash-seed:"
            + binding.binding_sha256.removeprefix("sha256:")
        )
        snapshot = PaperPortfolioSnapshot(
            snapshot_id=(
                f"{binding.portfolio_id}-cash-seed-{seed_date.replace('-', '')}"
            ),
            portfolio_id=binding.portfolio_id,
            decision_date=seed_date,
            source_result_id=source_result_id,
            cash=policy.initial_capital,
            total_value=policy.initial_capital,
            positions=(),
        )
        receipt = PaperPortfolioSnapshotReceipt.account_cash_seed_for(
            snapshot,
            account_namespace=binding.account_namespace,
            binding_sha256=binding.binding_sha256,
            seed_created_at=created_at_text,
        )
        store_paths = PersonalPaperStorePaths.from_route(
            selection.route,
            portfolio_id=binding.portfolio_id,
        )
        repository = PaperPortfolioSnapshotRepository(
            store_paths.state_db,
            route=selection.route,
            portfolio_id=binding.portfolio_id,
            personal_paths=self.personal_paths,
        )
        try:
            repository.append_account_cash_seed_once(snapshot, receipt)
        except ValueError as exc:
            if str(exc) == "strategy_account_seed_already_exists":
                raise StrategyPaperAccountSeedError(
                    "strategy_account_seed_already_exists"
                ) from exc
            raise
        saved_snapshot = repository.get(snapshot.snapshot_id)
        saved_receipt = repository.get_receipt(snapshot.snapshot_id)
        if saved_snapshot != snapshot or saved_receipt != receipt:
            raise StrategyPaperAccountSeedError("strategy_account_seed_readback_mismatch")
        return StrategyPaperAccountCashSeed(snapshot=snapshot, receipt=receipt)


__all__ = [
    "StrategyPaperAccountCashSeed",
    "StrategyPaperAccountCashSeedWriter",
    "StrategyPaperAccountSeedError",
]
