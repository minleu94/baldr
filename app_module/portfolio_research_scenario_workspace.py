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
from app_module.portfolio_research_initial_source import (
    PortfolioResearchInitialSourceProvider, InitialPortfolioResearchSelection, InitialPortfolioResearchCatalogue,
    InitialPortfolioAccountCatalogue,
)
from app_module.portfolio_research_registry import (
    PortfolioScenarioRegistryService, ScenarioRegistryEntry, ScenarioRegistrySelection,
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

    def __init__(self, repository: PortfolioResearchScenarioRepository, *,
                 initial_source_provider: PortfolioResearchInitialSourceProvider | None = None,
                 registry: PortfolioScenarioRegistryService | None = None) -> None:
        self.repository = repository
        self.initial_source_provider = initial_source_provider
        self.registry = registry

    @property
    def can_register(self) -> bool:
        return self.registry is not None and self.registry.can_register

    def register_saved(self, artifact_id: str, *, account_kind: str, portfolio_id: str,
                       cancel_callback=None) -> ScenarioRegistryEntry:
        if self.registry is None:
            raise ValueError("尚未配置研究 Registry")
        return self.registry.register_saved(artifact_id, account_kind=account_kind, portfolio_id=portfolio_id,
                                            cancel_callback=cancel_callback)

    def list_registered(self, *, account_kind: str, portfolio_id: str, cancel_callback=None) -> tuple[ScenarioRegistryEntry, ...]:
        if self.registry is None:
            raise ValueError("尚未配置研究 Registry")
        return self.registry.list_registered(account_kind=account_kind, portfolio_id=portfolio_id, cancel_callback=cancel_callback)

    def open_registered(self, selection: ScenarioRegistrySelection, *, cancel_callback=None) -> SavedPortfolioResearchScenario:
        if self.registry is None:
            raise ValueError("尚未配置研究 Registry")
        return self.registry.open_registered(selection, cancel_callback=cancel_callback)

    @property
    def can_create_initial(self) -> bool:
        return self.initial_source_provider is not None

    def list_initial_accounts(self, *, cancel_callback=None) -> InitialPortfolioAccountCatalogue:
        if self.initial_source_provider is None:
            raise ValueError("尚未配置策略帳與 Health 來源 reader")
        return self.initial_source_provider.list_account_identities(cancel_callback=cancel_callback)

    def list_initial_sources(self, *, strategy_id: str, strategy_version_id: str, account_namespace: str,
                             cancel_callback=None) -> InitialPortfolioResearchCatalogue:
        if self.initial_source_provider is None:
            raise ValueError("尚未配置策略帳與 Health 來源 reader")
        return self.initial_source_provider.list_sources(strategy_id=strategy_id, strategy_version_id=strategy_version_id,
                                                         account_namespace=account_namespace, cancel_callback=cancel_callback)

    def compare_initial(self, selection: InitialPortfolioResearchSelection, *, candidate_symbols: tuple[str, ...],
                        use_all_account_positions: bool = False,
                        explicit_weights: AllocationWeightContract | None = None, cancel_callback=None) -> PortfolioResearchScenarioComparison:
        if self.initial_source_provider is None:
            raise ValueError("尚未配置策略帳與 Health 來源 reader")
        return self.initial_source_provider.compare(selection, candidate_symbols=candidate_symbols,
                                                   use_all_account_positions=use_all_account_positions,
                                                   explicit_weights=explicit_weights, cancel_callback=cancel_callback)

    def save_initial(self, selection: InitialPortfolioResearchSelection, comparison: PortfolioResearchScenarioComparison, *,
                     cancel_callback=None) -> SavedPortfolioResearchScenario:
        if self.initial_source_provider is None:
            raise ValueError("尚未配置策略帳與 Health 來源 reader")
        verified = self.initial_source_provider.compare(
            selection, candidate_symbols=comparison.request.candidate_symbols,
            explicit_weights=comparison.request.explicit_weights, decision_at=comparison.request.decision_at,
            cancel_callback=cancel_callback,
        )
        if encode_scenario_artifact(verified) != encode_scenario_artifact(comparison):
            raise ValueError("待保存內容與原始來源重新比較不符")
        _check_cancel(cancel_callback)
        return self.repository.append(verified, saved_at=datetime.now(timezone.utc))

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
