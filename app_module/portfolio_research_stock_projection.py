"""原配置封存的單股唯讀投影；不查目前帳戶、不重跑配置或推論。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.portfolio_research_scenario_repository import SavedPortfolioResearchScenario


@dataclass(frozen=True, slots=True)
class PortfolioScenarioStockReference:
    account_kind: str
    portfolio_id: str
    artifact_id: str

    def __post_init__(self) -> None:
        if self.account_kind not in {'manual', 'user_declared', 'paper'}:
            raise ValueError('封存帳種不符')
        if type(self.portfolio_id) is not str or not self.portfolio_id or self.portfolio_id != self.portfolio_id.strip():
            raise ValueError('必須明選原portfolio_id')
        if type(self.artifact_id) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', self.artifact_id) is None:
            raise ValueError('必須明選原封存hash')

    @classmethod
    def from_mapping(cls, value: object) -> PortfolioScenarioStockReference:
        if type(value) is not dict or set(value) != {'account_kind', 'portfolio_id', 'artifact_id'}:
            raise ValueError('封存參照欄位不符')
        return cls(**value)


@dataclass(frozen=True, slots=True)
class PortfolioScenarioStockTarget:
    scenario_kind: str
    rule_requested_weight_bp: int | None
    target_weight_bp: int | None
    current_weight_bp: int | None
    gap_weight_bp: int | None
    executable_shares: int | None
    executable_amount: Decimal | None
    estimated_cost: Decimal | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioScenarioStockProjection:
    reference: PortfolioScenarioStockReference
    stock_code: str
    snapshot_id: str
    account_as_of_date: str
    account_available_at: str
    decision_at: str
    account_source_hash: str
    research_source_hash: str
    context_source_hash: str
    context_available_at: str
    cash_amount: Decimal
    total_value: Decimal
    quantity: int
    mark_price: Decimal | None
    market_value: Decimal | None
    current_weight_bp: int
    health_state: str
    health_known: bool
    targets: tuple[PortfolioScenarioStockTarget, ...]


def project_saved_scenario_stock(
    saved: SavedPortfolioResearchScenario, *, reference: PortfolioScenarioStockReference,
    stock_code: str, expected_account_source_hash: str,
) -> PortfolioScenarioStockProjection:
    """只投影原public exact reader回傳；外層來源hash與三重帳本身分都須相同。"""
    from app_module.portfolio_research_scenario_repository import SavedPortfolioResearchScenario
    from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact, scenario_artifact_id
    if type(saved) is not SavedPortfolioResearchScenario or type(reference) is not PortfolioScenarioStockReference:
        raise ValueError('必須先精確重讀原封存')
    comparison = saved.comparison
    if scenario_artifact_id(encode_scenario_artifact(comparison)) != saved.artifact_id:
        raise ValueError('封存內容與原artifact hash不符')
    account = comparison.account
    if (saved.artifact_id, account.account_kind, account.portfolio_id) != (
        reference.artifact_id, reference.account_kind, reference.portfolio_id,
    ) or account.source_hash != expected_account_source_hash:
        raise ValueError('封存參照與原帳本來源不符')
    universe = set(comparison.request.candidate_symbols) | {row.stock_code for row in account.positions}
    if stock_code not in universe:
        raise ValueError('股票不在原候選及完整持倉範圍')
    contexts = [row for row in comparison.request.contexts if row.context.stock_code == stock_code]
    if len(contexts) != 1:
        raise ValueError('原封存單股context缺件或重複')
    context = contexts[0]
    position = next((row for row in account.valuation.positions if row.stock_code == stock_code), None)
    targets = []
    for scenario in comparison.scenarios:
        rows = [row for row in scenario.result.projection.rows if row.stock_code == stock_code]
        if len(rows) > 1:
            raise ValueError('原情境單股列重複')
        row = rows[0] if rows else None
        targets.append(PortfolioScenarioStockTarget(
            scenario.scenario_kind,
            row.rule_requested_weight_bp if row else None, row.target_weight_bp if row else None,
            row.current_weight_bp if row else None, row.gap_weight_bp if row else None,
            row.executable_shares if row else None, row.executable_amount if row else None,
            row.estimated_cost if row else None, tuple(row.diagnostics) if row else (),
        ))
    return PortfolioScenarioStockProjection(
        reference=reference, stock_code=stock_code, snapshot_id=account.snapshot_id,
        account_as_of_date=account.as_of_date, account_available_at=account.available_at.isoformat(),
        decision_at=comparison.decision_at.isoformat(), account_source_hash=account.source_hash,
        research_source_hash=comparison.research_source_hash, context_source_hash=context.source_hash,
        context_available_at=context.available_at.isoformat(), cash_amount=account.valuation.cash_amount,
        total_value=account.valuation.total_value, quantity=position.quantity if position else 0,
        mark_price=position.mark_price if position else None, market_value=position.market_value if position else None,
        current_weight_bp=account.current_weights.symbol_weights_bp.get(stock_code, 0),
        health_state=context.context.health_state, health_known=context.health_known, targets=tuple(targets),
    )
