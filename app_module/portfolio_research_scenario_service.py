"""已選帳本的人選配置情境；共用既有 Construction／Allocation 計算。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, localcontext
from typing import Any, Mapping, Protocol
from zoneinfo import ZoneInfo

from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract,
    CausalPortfolioState,
    PortfolioAllocationContextRow,
    PortfolioAllocationProjectionV1,
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
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition
from financial_module.units import quantize_money


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
    valuation: PortfolioResearchValuation

    def __post_init__(self) -> None:
        if self.account_kind not in _ACCOUNT_KINDS:
            raise ValueError("unsupported account_kind")
        for name in ("portfolio_id", "snapshot_id"):
            object.__setattr__(self, name, _validate_non_empty(name, getattr(self, name)))
        _validate_iso_date("as_of_date", self.as_of_date)
        _aware("available_at", self.available_at)
        _validate_sha256("source_hash", self.source_hash)
        _validate_decimal("capital_amount", self.capital_amount, positive=True)
        if not isinstance(self.valuation, PortfolioResearchValuation):
            raise ValueError("complete exact valuation required; cash cannot be inferred from bp")
        if self.capital_amount != self.valuation.total_value or self.current_weights != self.valuation.display_weights:
            raise ValueError("account capital or weights differ from exact valuation")
        if not isinstance(self.current_weights, AllocationWeightContract):
            raise ValueError("complete current_weights are required; unknown is not zero")
        if not isinstance(self.positions, tuple) or any(
            not isinstance(position, PortfolioResearchPosition) for position in self.positions
        ):
            raise ValueError("positions must be a tuple of PortfolioResearchPosition")
        symbols = [position.stock_code for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate account position")
        if {row.stock_code: row.quantity for row in self.positions} != {
            row.stock_code: row.quantity for row in self.valuation.positions
        }:
            raise ValueError("positions must match the complete valued quantity universe")

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
            "valuation": self.valuation.to_dict(),
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
    snapshot_id: str
    context: PortfolioAllocationContextRow
    available_at: datetime
    source_hash: str
    health_known: bool

    def __post_init__(self) -> None:
        if self.account_kind not in _ACCOUNT_KINDS:
            raise ValueError("unsupported context account_kind")
        for name in ("portfolio_id", "snapshot_id"):
            value = _validate_non_empty(name, getattr(self, name))
            if value != getattr(self, name):
                raise ValueError(f"context {name} must be canonical")
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
            "snapshot_id": self.snapshot_id,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_kind": self.account_kind,
            "portfolio_id": self.portfolio_id,
            "snapshot_id": self.snapshot_id,
            "decision_at": self.decision_at.isoformat(),
            "candidate_symbols": sorted(self.candidate_symbols),
            "contexts": [item.to_dict() for item in sorted(self.contexts, key=lambda item: item.context.stock_code)],
            "research_source_hash": self.research_source_hash,
            "explicit_weights": self.explicit_weights.to_dict() if self.explicit_weights is not None else None,
            "weekly_turnover_used_bp": self.weekly_turnover_used_bp,
        }


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
    request: PortfolioResearchScenarioRequest

    def __post_init__(self) -> None:
        if not isinstance(self.account, PortfolioResearchAccountState) or not isinstance(self.request, PortfolioResearchScenarioRequest):
            raise ValueError("comparison requires typed account and request")
        _aware("decision_at", self.decision_at)
        _validate_sha256("input_hash", self.input_hash)
        if self.decision_at != self.request.decision_at or self.research_source_hash != self.request.research_source_hash:
            raise ValueError("comparison clock or research source differs from request")
        contexts = _validate_scenario_sources(self.account, self.request)
        expected_kinds = ("maintain", "equal_weight") + (("explicit_target",) if self.request.explicit_weights is not None else ())
        if not isinstance(self.scenarios, tuple) or any(not isinstance(item, PortfolioResearchScenario) for item in self.scenarios):
            raise ValueError("comparison requires typed scenarios")
        if tuple(item.scenario_kind for item in self.scenarios) != expected_kinds:
            raise ValueError("comparison scenario kinds are incomplete or reordered")
        policy_hashes = {item.result.allocation_policy_hash for item in self.scenarios}
        if len(policy_hashes) != 1:
            raise ValueError("comparison mixes allocation policies")
        policy_hash = next(iter(policy_hashes))
        if self.input_hash != _payload_hash(_scenario_input_payload(self.account, self.request, policy_hash)):
            raise ValueError("comparison input hash mismatch")
        causal = CausalPortfolioState.create_valued(as_of_date=self.account.as_of_date, valuation=self.account.valuation)
        day = self.decision_at.astimezone(_TAIPEI).date().isoformat()
        symbols = set(self.request.candidate_symbols) | set(self.account.current_weights.symbol_weights_bp)
        for item in self.scenarios:
            result = item.result
            if result.source_hash != self.input_hash or result.decision_date != day or result.causal_portfolio_state_hash != causal.state_hash:
                raise ValueError("scenario source, clock or account state mismatch")
            if result.rule_policy_hash != _payload_hash({"schema": "human-portfolio-scenario.v1", "scenario_kind": item.scenario_kind}):
                raise ValueError("scenario rule policy mismatch")
            if result.projection.current_cash_bp != self.account.current_weights.cash_weight_bp:
                raise ValueError("scenario current cash mismatch")
            if {row.stock_code for row in result.projection.rows} != symbols:
                raise ValueError("scenario row universe mismatch")
            weight_contracts = (result.requested_weights, result.projection.target_weights,
                result.projection.executable_weights)
            if any(contract is not None and set(contract.symbol_weights_bp) - symbols for contract in weight_contracts):
                raise ValueError("scenario weight universe contains hidden symbols")
            if result.projection.total_estimated_cost != sum((row.estimated_cost for row in result.projection.rows), Decimal("0")):
                raise ValueError("scenario total cost differs from saved rows")
            _validate_frozen_money(self.account, result.projection, contexts)
            for row in result.projection.rows:
                if row.current_weight_bp != self.account.current_weights.weight_for(row.stock_code):
                    raise ValueError("scenario current weight mismatch")
                if row.rule_requested_weight_bp != result.requested_weights.weight_for(row.stock_code) or row.blended_weight_bp != row.rule_requested_weight_bp or row.ml_requested_weight_bp != 0:
                    raise ValueError("scenario requested weights mismatch")
                if row.target_weight_bp != result.projection.target_weights.weight_for(row.stock_code):
                    raise ValueError("scenario target row mismatch")
                context = contexts[row.stock_code].context
                if row.reference_price != context.reference_price or row.stock_name != context.stock_name:
                    raise ValueError("scenario price or name differs from saved context")
                if row.gap_weight_bp != row.target_weight_bp - self.account.current_weights.weight_for(row.stock_code):
                    raise ValueError("scenario gap differs from current and target")
                if result.projection.executable_weights is not None and row.executable_weight_bp != result.projection.executable_weights.weight_for(row.stock_code):
                    raise ValueError("scenario executable row mismatch")
                if result.projection.executable_weights is None and (
                    row.executable_weight_bp is not None or row.executable_shares is not None
                    or row.executable_amount != Decimal("0") or row.estimated_cost != Decimal("0")
                ):
                    raise ValueError("scenario has executable rows without complete weights")
            if item.scenario_kind == "maintain" and result.requested_weights != self.account.current_weights:
                raise ValueError("maintain scenario differs from current account")
            if item.scenario_kind == "explicit_target" and result.requested_weights != self.request.explicit_weights:
                raise ValueError("explicit scenario differs from human target")
            if item.scenario_kind == "equal_weight":
                ordered = sorted(self.request.candidate_symbols)
                weight, remainder = divmod(10000, len(ordered))
                expected = AllocationWeightContract({symbol: weight + int(index < remainder)
                    for index, symbol in enumerate(ordered)}, 0)
                if result.requested_weights != expected:
                    raise ValueError("equal scenario differs from selected candidate universe")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "portfolio-research-scenarios.v3",
            "account": self.account.to_dict(),
            "decision_at": self.decision_at.isoformat(),
            "research_source_hash": self.research_source_hash,
            "input_hash": self.input_hash,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "request": self.request.to_dict(),
            "research_only": True,
            "broker_order_allowed": False,
            "apply_rebalance": False,
        }


def _validate_frozen_money(
    account: PortfolioResearchAccountState,
    projection: PortfolioAllocationProjectionV1,
    contexts: Mapping[str, PortfolioResearchContextEvidence],
) -> None:
    """核 v3 封存金額守恆及固定成本，不重新產生配置或讀當下行情。"""
    if projection.executable_weights is None:
        if projection.post_cost_cash_amount != account.valuation.cash_amount or projection.total_estimated_cost != Decimal("0"):
            raise ValueError("discarded scenario changed original cash or cost")
        return
    prior = {row.stock_code: row for row in account.valuation.positions}
    final_positions = []
    with localcontext(Context(prec=60)):
        expected_cash = account.valuation.cash_amount
        for row in projection.rows:
            quantity = row.executable_shares
            if quantity is None:
                raise ValueError("complete scenario has unknown executable shares")
            price = contexts[row.stock_code].context.reference_price
            before = prior.get(row.stock_code)
            delta = quantity - (before.quantity if before is not None else 0)
            if quantity > 0:
                if price is None:
                    raise ValueError("scenario held position price missing")
                final_positions.append(PortfolioResearchValuedPosition(row.stock_code, quantity, price, row.executable_amount))
            elif row.executable_amount != Decimal("0"):
                raise ValueError("scenario empty position has nonzero market value")
            if delta:
                if price is None:
                    raise ValueError("scenario changed quantity without reference price")
                notional = quantize_money(Decimal(abs(delta)) * price)
                # v3 封存契約固定沿既有每邊成本：買 25bp、賣 55bp。
                expected_cost = quantize_money(notional * Decimal(25 if delta > 0 else 55) / Decimal(10000))
                if row.estimated_cost != expected_cost:
                    raise ValueError("scenario frozen trade cost mismatch")
                expected_cash += (-notional if delta > 0 else notional) - expected_cost
            elif row.estimated_cost != Decimal("0"):
                raise ValueError("unchanged scenario position has trade cost")
        if projection.post_cost_cash_amount != expected_cash:
            raise ValueError("scenario frozen cash movement mismatch")
        final_nav = projection.post_cost_cash_amount + sum((row.executable_amount for row in projection.rows), Decimal("0"))
        final = PortfolioResearchValuation(projection.post_cost_cash_amount, final_nav, tuple(final_positions))
        if projection.executable_weights != final.display_weights:
            raise ValueError("scenario frozen weights differ from complete final valuation")


def _scenario_input_payload(
    account: PortfolioResearchAccountState, request: PortfolioResearchScenarioRequest,
    allocation_policy_hash: str,
) -> dict[str, Any]:
    return {
        "schema": "portfolio-research-input.v3",
        "account": account.to_dict(), "request": request.to_dict(),
        "allocation_policy_hash": allocation_policy_hash,
    }


def _validate_scenario_sources(
    account: PortfolioResearchAccountState, request: PortfolioResearchScenarioRequest
) -> dict[str, PortfolioResearchContextEvidence]:
    if (account.account_kind, account.portfolio_id, account.snapshot_id) != (
        request.account_kind, request.portfolio_id, request.snapshot_id
    ):
        raise ValueError("selected account identity mismatch")
    decision_date = request.decision_at.astimezone(_TAIPEI).date().isoformat()
    if account.available_at > request.decision_at or account.as_of_date >= decision_date:
        raise ValueError("account state was not available strictly before decision date")
    contexts = {item.context.stock_code: item for item in request.contexts}
    symbols = set(request.candidate_symbols) | set(account.current_weights.symbol_weights_bp)
    if request.explicit_weights is not None and set(request.explicit_weights.symbol_weights_bp) - symbols:
        raise ValueError("explicit target contains an unselected symbol")
    if set(contexts) != symbols:
        raise ValueError("context universe must match candidates plus all account holdings")
    quantities = {position.stock_code: position.quantity for position in account.positions}
    marks = {position.stock_code: position.mark_price for position in account.valuation.positions}
    for symbol, evidence in contexts.items():
        if (evidence.account_kind, evidence.portfolio_id) != (account.account_kind, account.portfolio_id):
            raise ValueError("context belongs to another account")
        if evidence.snapshot_id != account.snapshot_id:
            raise ValueError("context belongs to another account snapshot")
        if evidence.available_at > request.decision_at:
            raise ValueError("context became available after decision")
        if not evidence.health_known:
            raise ValueError("health evidence unavailable; unknown is not healthy")
        row = evidence.context
        if row.current_weight_bp != account.current_weights.weight_for(symbol):
            raise ValueError("context current weight differs from exact account state")
        if row.current_shares != quantities.get(symbol, 0):
            raise ValueError("context shares differ from exact complete account state")
        if symbol in marks and row.reference_price != marks[symbol]:
            raise ValueError("context price differs from exact account valuation")
        if row.market_data_as_of_date is not None:
            _validate_iso_date("market_data_as_of_date", row.market_data_as_of_date)
            if row.market_data_as_of_date >= decision_date:
                raise ValueError("market data is not strictly prior to decision date")
    return contexts


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
        decision_date = request.decision_at.astimezone(_TAIPEI).date().isoformat()
        contexts = _validate_scenario_sources(account, request)
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
        input_hash = _payload_hash(_scenario_input_payload(account, request, self._allocation.allocation_policy_hash))
        causal = CausalPortfolioState.create_valued(
            as_of_date=account.as_of_date, valuation=account.valuation,
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
            request=request,
        )
