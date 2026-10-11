"""將明示策略 Paper checkpoint 接入持倉情境的完整帳戶讀取契約。

本 adapter 只消費公開 exact reader 已核的帳本來源，不自行查 latest、推定
Health 或推算現金。Manual／user_declared 帳戶必須使用各自的來源 reader。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app_module.portfolio_allocation_dtos import _payload_hash
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState,
    PortfolioResearchPosition,
)
from app_module.portfolio_research_valuation import PortfolioResearchValuation
from app_module.strategy_paper_account_availability import (
    read_exact_strategy_paper_account_checkpoint,
)
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountService,
)


@dataclass(frozen=True, slots=True)
class StrategyPaperResearchCheckpointSelection:
    """使用者已選的來源身分；不包含 caller 宣稱的 hashes 或可得時間。"""

    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    operation_id: str
    snapshot_id: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"research_checkpoint_selection_{name}_invalid")


class StrategyPaperPortfolioResearchAccountReader:
    """綁定明示 checkpoint 與本次決策時計的策略 Paper 帳戶 reader。"""

    def __init__(
        self,
        account_service: StrategyPaperAccountService,
        selection: StrategyPaperResearchCheckpointSelection,
        *,
        decision_cutoff: datetime,
    ) -> None:
        if not isinstance(selection, StrategyPaperResearchCheckpointSelection):
            raise ValueError("research_checkpoint_selection_required")
        if (
            not isinstance(decision_cutoff, datetime)
            or decision_cutoff.tzinfo is None
            or decision_cutoff.utcoffset() is None
        ):
            raise ValueError("research_account_decision_cutoff_timezone_unknown")
        self._service = account_service
        self._selection = selection
        self._decision_cutoff = decision_cutoff.astimezone(timezone.utc)

    def read_exact(
        self, *, account_kind: str, portfolio_id: str, snapshot_id: str
    ) -> PortfolioResearchAccountState:
        selection = self._selection
        if account_kind != "paper":
            raise ValueError("strategy_research_reader_requires_paper_account")
        if snapshot_id != selection.snapshot_id:
            raise ValueError("research_account_snapshot_selection_mismatch")
        selected = self._service.select_exact_version(
            strategy_id=selection.strategy_id,
            strategy_version_id=selection.strategy_version_id,
            account_namespace=selection.account_namespace,
        )
        if selected.status is not AccountBindingStatus.READY or selected.binding is None:
            raise ValueError("research_account_binding_unavailable")
        if portfolio_id != selected.binding.portfolio_id:
            raise ValueError("research_account_portfolio_selection_mismatch")
        checkpoint = read_exact_strategy_paper_account_checkpoint(
            self._service,
            strategy_id=selection.strategy_id,
            strategy_version_id=selection.strategy_version_id,
            account_namespace=selection.account_namespace,
            operation_id=selection.operation_id,
            snapshot_id=selection.snapshot_id,
            decision_cutoff=self._decision_cutoff,
        )
        if (
            checkpoint.binding != selected.binding
            or checkpoint.snapshot.snapshot_id != snapshot_id
            or checkpoint.snapshot.portfolio_id != portfolio_id
        ):
            raise ValueError("research_account_exact_checkpoint_mismatch")
        valuation = PortfolioResearchValuation.from_snapshot(checkpoint.snapshot)
        # 綁實際來源的各層身分；content hash 不另授來源時效或績效資格。
        source_hash = _payload_hash({
            "schema_version": "portfolio-research-strategy-paper-source.v1",
            "binding_sha256": checkpoint.binding.binding_sha256,
            "operation_id": selection.operation_id,
            "operation_sha256": checkpoint.operation_sha256,
            "snapshot_id": snapshot_id,
            "snapshot_sha256": checkpoint.availability.snapshot_sha256,
            "base_receipt_sha256": checkpoint.availability.base_receipt_sha256,
            "availability_receipt_sha256": checkpoint.availability.receipt_sha256,
            "ledger_operation_sha256": checkpoint.ledger_operation.operation_sha256,
        })
        return PortfolioResearchAccountState(
            account_kind="paper",
            portfolio_id=portfolio_id,
            snapshot_id=snapshot_id,
            as_of_date=checkpoint.snapshot.decision_date,
            available_at=checkpoint.availability.available_at,
            source_hash=source_hash,
            capital_amount=valuation.total_value,
            current_weights=valuation.display_weights,
            positions=tuple(
                PortfolioResearchPosition(row.stock_code, row.quantity)
                for row in valuation.positions
            ),
            valuation=valuation,
        )
