"""沿既有情境封存重開與另存假設；不把舊證據改稱今日帳本。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from app_module.portfolio_allocation_dtos import AllocationWeightContract
from app_module.portfolio_allocation_service import PortfolioAllocationService
from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact, scenario_artifact_id
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository, SavedPortfolioResearchScenario,
)
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState, PortfolioResearchScenarioComparison,
    PortfolioResearchScenarioService,
)


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise InterruptedError("研究操作已取消")


class _FrozenAccountReader:
    def __init__(self, account: PortfolioResearchAccountState) -> None:
        self.account = account

    def read_exact(self, *, account_kind: str, portfolio_id: str, snapshot_id: str) -> PortfolioResearchAccountState:
        if (account_kind, portfolio_id, snapshot_id) != (
            self.account.account_kind, self.account.portfolio_id, self.account.snapshot_id,
        ):
            raise ValueError("封存帳本身分不符")
        return self.account


class PortfolioResearchScenarioWorkspace:
    """只從既有完整封存取事實，研究新 target；首次來源建立另循原 reader。"""

    def __init__(self, repository: PortfolioResearchScenarioRepository) -> None:
        self.repository = repository

    @property
    def can_save(self) -> bool:
        return self.repository.writable

    def list_saved(self, *, account_kind: str, portfolio_id: str, cancel_callback=None) -> tuple[str, ...]:
        _check_cancel(cancel_callback)
        result = self.repository.list_artifact_ids(account_kind=account_kind, portfolio_id=portfolio_id, limit=25)
        _check_cancel(cancel_callback)
        return result

    def open_exact(self, artifact_id: str, *, account_kind: str, portfolio_id: str, cancel_callback=None) -> SavedPortfolioResearchScenario:
        _check_cancel(cancel_callback)
        result = self.repository.get_exact(artifact_id, account_kind=account_kind, portfolio_id=portfolio_id)
        _check_cancel(cancel_callback)
        if result is None:
            raise ValueError("所選帳本沒有這份已保存情境")
        return result

    def compare_target(self, artifact_id: str, *, account_kind: str, portfolio_id: str,
                       explicit_weights: AllocationWeightContract, cancel_callback=None) -> PortfolioResearchScenarioComparison:
        saved = self.open_exact(artifact_id, account_kind=account_kind, portfolio_id=portfolio_id,
                                cancel_callback=cancel_callback)
        original = saved.comparison
        allocation = PortfolioAllocationService()
        if any(row.result.allocation_policy_hash != allocation.allocation_policy_hash for row in original.scenarios):
            raise ValueError("封存配置政策版本與現行不同；仍可讀回，不能用新政策重算舊情境")
        _check_cancel(cancel_callback)
        request = replace(original.request, explicit_weights=explicit_weights)
        result = PortfolioResearchScenarioService(_FrozenAccountReader(original.account), allocation=allocation).compare(request)
        _check_cancel(cancel_callback)
        return result

    def save_target(self, artifact_id: str, comparison: PortfolioResearchScenarioComparison, *,
                    account_kind: str, portfolio_id: str, cancel_callback=None) -> SavedPortfolioResearchScenario:
        """重核原件與唯一可變 target，再交原 append；成功後另存新 hash。"""
        if comparison.request.explicit_weights is None:
            raise ValueError("另存假設必須有明示 target")
        verified = self.compare_target(artifact_id, account_kind=account_kind, portfolio_id=portfolio_id,
                                       explicit_weights=comparison.request.explicit_weights,
                                       cancel_callback=cancel_callback)
        if encode_scenario_artifact(verified) != encode_scenario_artifact(comparison):
            raise ValueError("待保存內容不是從所選封存的明示 target 產生")
        _check_cancel(cancel_callback)
        return self.repository.append(verified, saved_at=datetime.now(timezone.utc))

    @staticmethod
    def artifact_id(comparison: PortfolioResearchScenarioComparison) -> str:
        return scenario_artifact_id(encode_scenario_artifact(comparison))
