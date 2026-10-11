"""已選帳本的人選配置情境；共用既有 Construction／Allocation 計算。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract,
    CausalPortfolioState,
    PortfolioAllocationContextRow,
    PortfolioRuleAllocationRequestV1,
    PortfolioRuleAllocationResultV1,
    _payload_hash,
    _validate_decimal,
    _validate_int,
    _validate_iso_date,
    _validate_non_empty,
    _validate_sha256,
)
from app_module.portfolio_allocation_service import PortfolioAllocationService
from app_module.portfolio_construction_dtos import (
    PortfolioConstructionCandidate,
    PortfolioConstructionRequest,
)
from app_module.portfolio_construction_service import PortfolioConstructionService


_TAIPEI = ZoneInfo("Asia/Taipei")
_ACCOUNT_KINDS = frozenset({"manual", "user_declared", "paper"})


def _aware(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True)
class PortfolioResearchPosition:
    stock_code: str
    quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "stock_code", _validate_non_empty("stock_code", self.stock_code))
        _validate_int("quantity", self.quantity, minimum=1)


@dataclass(frozen=True)
class PortfolioResearchAccountState:
    """由完整帳本 reader 產出的同份狀態；source_hash 指向原始保存證據。"""

    account_kind: str
    portfolio_id: str
    snapshot_id: str
    as_of_date: str
    available_at: datetime
    source_hash: str
    capital_amount: Decimal
    current_weights: AllocationWeightContract
    positions: tuple[PortfolioResearchPosition, ...]

    def __post_init__(self) -> None:
        if self.account_kind not in _ACCOUNT_KINDS:
            raise ValueError("unsupported account_kind")
        for name in ("portfolio_id", "snapshot_id"):
            object.__setattr__(self, name, _validate_non_empty(name, getattr(self, name)))
        _validate_iso_date("as_of_date", self.as_of_date)
        _aware("available_at", self.available_at)
        _validate_sha256("source_hash", self.source_hash)
        _validate_decimal("capital_amount", self.capital_amount, positive=True)
        if not isinstance(self.current_weights, AllocationWeightContract):
            raise ValueError("complete current_weights are required; unknown is not zero")
        if not isinstance(self.positions, tuple) or any(
            not isinstance(position, PortfolioResearchPosition) for position in self.positions
        ):
            raise ValueError("positions must be a tuple of PortfolioResearchPosition")
        symbols = [position.stock_code for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate account position")
        if set(symbols) != {
            code for code, weight in self.current_weights.symbol_weights_bp.items() if weight > 0
        }:
            raise ValueError("positions must match the complete positive-weight universe")
        if any(weight == 0 for weight in self.current_weights.symbol_weights_bp.values()):
            raise ValueError("complete account state must omit zero-weight positions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_kind": self.account_kind,
            "portfolio_id": self.portfolio_id,
            "snapshot_id": self.snapshot_id,
            "as_of_date": self.as_of_date,
            "available_at": self.available_at.isoformat(),
            "source_hash": self.source_hash,
            "capital_amount": str(self.capital_amount),
            "current_weights": self.current_weights.to_dict(),
            "positions": [{"stock_code": p.stock_code, "quantity": p.quantity} for p in self.positions],
        }


class PortfolioResearchAccountReader(Protocol):
    def read_exact(
        self, *, account_kind: str, portfolio_id: str, snapshot_id: str
    ) -> PortfolioResearchAccountState:
        """讀取已選帳本的完整 exact snapshot；不得猜 latest 或改寫來源。"""
        ...


@dataclass(frozen=True)
class PortfolioResearchContextEvidence:
    """同股風控／行情證據及其帳本、可得時鐘；缺 Health 不推定健康。"""

    account_kind: str
    portfolio_id: str
    context: PortfolioAllocationContextRow
    available_at: datetime
    source_hash: str
    health_known: bool

    def __post_init__(self) -> None:
        if self.account_kind not in _ACCOUNT_KINDS:
            raise ValueError("unsupported context account_kind")
        _validate_non_empty("portfolio_id", self.portfolio_id)
        if not isinstance(self.context, PortfolioAllocationContextRow):
            raise ValueError("context must be PortfolioAllocationContextRow")
        _aware("context.available_at", self.available_at)
        _validate_sha256("context.source_hash", self.source_hash)
        if type(self.health_known) is not bool:
            raise ValueError("health_known must be bool")

    def to_dict(self) -> dict[str, Any]:
        row = self.context
        return {
            "account_kind": self.account_kind,
            "portfolio_id": self.portfolio_id,
            "available_at": self.available_at.isoformat(),
            "source_hash": self.source_hash,
            "health_known": self.health_known,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "current_weight_bp": row.current_weight_bp,
            "current_shares": row.current_shares,
            "sector_id": row.sector_id,
            "health_state": row.health_state,
            "hard_risk_reasons": list(row.hard_risk_reasons),
            "reference_price": str(row.reference_price) if row.reference_price is not None else None,
            "median_volume_20d_shares": row.median_volume_20d_shares,
            "market_data_as_of_date": row.market_data_as_of_date,
            "trading_days_since_last_trade": row.trading_days_since_last_trade,
        }


@dataclass(frozen=True)
class PortfolioResearchScenarioRequest:
    account_kind: str
    portfolio_id: str
    snapshot_id: str
    decision_at: datetime
    candidate_symbols: tuple[str, ...]
    contexts: tuple[PortfolioResearchContextEvidence, ...]
    research_source_hash: str
    explicit_weights: AllocationWeightContract | None = None
    weekly_turnover_used_bp: int = 0

    def __post_init__(self) -> None:
        if self.account_kind not in _ACCOUNT_KINDS:
            raise ValueError("unsupported account_kind")
        for name in ("portfolio_id", "snapshot_id"):
            _validate_non_empty(name, getattr(self, name))
        _aware("decision_at", self.decision_at)
        _validate_sha256("research_source_hash", self.research_source_hash)
        if not isinstance(self.candidate_symbols, tuple) or not self.candidate_symbols:
            raise ValueError("candidate_symbols must be a nonempty tuple")
        for symbol in self.candidate_symbols:
            if _validate_non_empty("candidate_symbol", symbol) != symbol:
                raise ValueError("candidate symbols must be canonical")
        if len(set(self.candidate_symbols)) != len(self.candidate_symbols):
            raise ValueError("duplicate candidate symbol")
        if not isinstance(self.contexts, tuple) or any(
            not isinstance(item, PortfolioResearchContextEvidence) for item in self.contexts
        ):
            raise ValueError("contexts must be a tuple of PortfolioResearchContextEvidence")
        if len({item.context.stock_code for item in self.contexts}) != len(self.contexts):
            raise ValueError("duplicate context symbol")
        if self.explicit_weights is not None and not isinstance(self.explicit_weights, AllocationWeightContract):
            raise ValueError("explicit_weights must be AllocationWeightContract")
        _validate_int("weekly_turnover_used_bp", self.weekly_turnover_used_bp, minimum=0, maximum=10000)


@dataclass(frozen=True)
class PortfolioResearchScenario:
    scenario_kind: str
    result: PortfolioRuleAllocationResultV1

    def to_dict(self) -> dict[str, Any]:
        return {"scenario_kind": self.scenario_kind, "result": self.result.to_dict()}


@dataclass(frozen=True)
class PortfolioResearchScenarioComparison:
    account: PortfolioResearchAccountState
    decision_at: datetime
    research_source_hash: str
    input_hash: str
    scenarios: tuple[PortfolioResearchScenario, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "portfolio-research-scenarios.v1",
            "account": self.account.to_dict(),
            "decision_at": self.decision_at.isoformat(),
            "research_source_hash": self.research_source_hash,
            "input_hash": self.input_hash,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "research_only": True,
            "broker_order_allowed": False,
            "apply_rebalance": False,
        }


class PortfolioResearchScenarioService:
    def __init__(
        self, account_reader: PortfolioResearchAccountReader,
        *, allocation: PortfolioAllocationService | None = None,
        construction: PortfolioConstructionService | None = None,
    ) -> None:
        self._reader = account_reader
        self._allocation = allocation or PortfolioAllocationService()
        self._construction = construction or PortfolioConstructionService()

    def compare(self, request: PortfolioResearchScenarioRequest) -> PortfolioResearchScenarioComparison:
        account = self._reader.read_exact(
            account_kind=request.account_kind, portfolio_id=request.portfolio_id,
            snapshot_id=request.snapshot_id,
        )
        if not isinstance(account, PortfolioResearchAccountState):
            raise ValueError("reader must return complete PortfolioResearchAccountState")
        if (account.account_kind, account.portfolio_id, account.snapshot_id) != (
            request.account_kind, request.portfolio_id, request.snapshot_id
        ):
            raise ValueError("selected account identity mismatch")
        decision_date = request.decision_at.astimezone(_TAIPEI).date().isoformat()
        if account.available_at > request.decision_at or date.fromisoformat(account.as_of_date) >= date.fromisoformat(decision_date):
            raise ValueError("account state was not available strictly before decision date")
        contexts = {item.context.stock_code: item for item in request.contexts}
        symbols = set(request.candidate_symbols) | set(account.current_weights.symbol_weights_bp)
        if request.explicit_weights is not None:
            if set(request.explicit_weights.symbol_weights_bp) - symbols:
                raise ValueError("explicit target contains an unselected symbol")
        if set(contexts) != symbols:
            raise ValueError("context universe must match candidates plus all account holdings")
        quantities = {position.stock_code: position.quantity for position in account.positions}
        for symbol, evidence in contexts.items():
            if (evidence.account_kind, evidence.portfolio_id) != (account.account_kind, account.portfolio_id):
                raise ValueError("context belongs to another account")
            if evidence.available_at > request.decision_at:
                raise ValueError("context became available after decision")
            if not evidence.health_known:
                raise ValueError("health evidence unavailable; unknown is not healthy")
            row = evidence.context
            if row.current_weight_bp != account.current_weights.weight_for(symbol):
                raise ValueError("context current weight differs from exact account state")
            if row.current_shares != quantities.get(symbol, 0):
                raise ValueError("context shares differ from exact complete account state")
            if row.market_data_as_of_date is not None:
                if date.fromisoformat(row.market_data_as_of_date) >= date.fromisoformat(decision_date):
                    raise ValueError("market data is not strictly prior to decision date")
        selected = tuple(contexts[symbol].context for symbol in sorted(request.candidate_symbols))
        if any(row.reference_price is None for row in selected):
            raise ValueError("equal weight comparison requires an exact price for each selected candidate")
        construction = self._construction.construct(PortfolioConstructionRequest(
            decision_date=decision_date, capital_amount=account.capital_amount,
            allocation_method="equal_weight",
            candidates=tuple(PortfolioConstructionCandidate(
                stock_code=row.stock_code, stock_name=row.stock_name, score_bp=0,
                reference_price=row.reference_price,
            ) for row in selected if row.reference_price is not None),
        ))
        equal_weights = AllocationWeightContract(
            {row.stock_code: row.target_weight_bp for row in construction.allocations}, 0
        )
        input_hash = _payload_hash({
            "schema": "portfolio-research-input.v1",
            "account": account.to_dict(), "decision_at": request.decision_at.isoformat(),
            "candidate_symbols": sorted(request.candidate_symbols),
            "contexts": [contexts[symbol].to_dict() for symbol in sorted(contexts)],
            "research_source_hash": request.research_source_hash,
            "explicit_weights": request.explicit_weights.to_dict() if request.explicit_weights is not None else None,
            "weekly_turnover_used_bp": request.weekly_turnover_used_bp,
            "allocation_policy_hash": self._allocation.allocation_policy_hash,
        })
        causal = CausalPortfolioState.create(
            as_of_date=account.as_of_date, current_weights=account.current_weights,
        )
        targets = [("maintain", account.current_weights), ("equal_weight", equal_weights)]
        if request.explicit_weights is not None:
            targets.append(("explicit_target", request.explicit_weights))
        scenarios = tuple(PortfolioResearchScenario(
            scenario_kind=kind,
            result=self._allocation.project_rule_only(PortfolioRuleAllocationRequestV1(
                decision_date=decision_date, capital_amount=account.capital_amount,
                rule_requested_weights=weights,
                contexts=tuple(contexts[symbol].context for symbol in sorted(contexts)),
                current_cash_bp=account.current_weights.cash_weight_bp,
                source_hash=input_hash,
                rule_policy_hash=_payload_hash({"schema": "human-portfolio-scenario.v1", "scenario_kind": kind}),
                weekly_turnover_used_bp=request.weekly_turnover_used_bp,
                causal_portfolio_state=causal,
            )),
        ) for kind, weights in targets)
        return PortfolioResearchScenarioComparison(
            account=account, decision_at=request.decision_at,
            research_source_hash=request.research_source_hash, input_hash=input_hash,
            scenarios=scenarios,
        )
