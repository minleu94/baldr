"""人選持倉情境的版本化封存；讀回原事實與結果，不重跑現行政策。"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract, PortfolioAllocationContextRow,
    PortfolioAllocationProjectionV1, PortfolioAllocationRowV2,
    PortfolioRuleAllocationResultV1,
)
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState, PortfolioResearchContextEvidence,
    PortfolioResearchPosition, PortfolioResearchScenario,
    PortfolioResearchScenarioComparison, PortfolioResearchScenarioRequest,
)
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition


MAX_SCENARIO_BYTES = 2 * 1024 * 1024


def _object(value: Any, names: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != names:
        raise ValueError("scenario artifact fields mismatch")
    return dict(value)


def _string(value: Any) -> str:
    if type(value) is not str:
        raise ValueError("scenario artifact requires a string")
    return value


def _list(value: Any) -> list[Any]:
    if type(value) is not list:
        raise ValueError("scenario artifact requires an array")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(_string(item) for item in _list(value))


def _money(value: Any) -> Decimal:
    text = _string(value)
    if len(text) > 128:
        raise ValueError("scenario artifact decimal exceeds limit")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("scenario artifact invalid decimal") from exc
    if not amount.is_finite() or abs(amount.adjusted()) > 100:
        raise ValueError("scenario artifact decimal outside finite bounds")
    return amount


def _clock(value: Any) -> datetime:
    result = datetime.fromisoformat(_string(value))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("scenario artifact requires aware clock")
    return result


def _weights(value: Any) -> AllocationWeightContract:
    data = _object(value, {"symbol_weights_bp", "cash_weight_bp", "total_weight_bp"})
    if type(data["total_weight_bp"]) is not int or data["total_weight_bp"] != 10000:
        raise ValueError("scenario artifact total weight mismatch")
    if type(data["symbol_weights_bp"]) is not dict:
        raise ValueError("scenario artifact symbol weights require an object")
    return AllocationWeightContract(data["symbol_weights_bp"], data["cash_weight_bp"])


def _account(value: Any) -> PortfolioResearchAccountState:
    data = _object(value, {field.name for field in fields(PortfolioResearchAccountState)})
    for name in ("account_kind", "portfolio_id", "snapshot_id", "as_of_date", "source_hash"):
        data[name] = _string(data[name])
    data["available_at"] = _clock(data["available_at"])
    data["capital_amount"] = _money(data["capital_amount"])
    data["valuation"] = _valuation(data["valuation"])
    data["current_weights"] = _weights(data["current_weights"])
    positions = []
    for value in _list(data["positions"]):
        position = _object(value, {"stock_code", "quantity"})
        positions.append(PortfolioResearchPosition(_string(position["stock_code"]), position["quantity"]))
    data["positions"] = tuple(positions)
    return PortfolioResearchAccountState(**data)


def _valuation(value: Any) -> PortfolioResearchValuation:
    data = _object(value, {"schema", "cash_amount", "total_value", "positions", "display_method", "display_weights"})
    if data["schema"] != "portfolio-research-valuation.v1" or data["display_method"] != "largest-remainder-bp.v1":
        raise ValueError("unsupported exact valuation schema or display method")
    positions = _list(data["positions"])
    if len(positions) > 10000:
        raise ValueError("exact valuation positions exceed limit")
    rows = []
    for value_row in positions:
        row = _object(value_row, {"stock_code", "quantity", "mark_price", "market_value"})
        rows.append(PortfolioResearchValuedPosition(_string(row["stock_code"]), row["quantity"],
            _money(row["mark_price"]), _money(row["market_value"])))
    valuation = PortfolioResearchValuation(_money(data["cash_amount"]), _money(data["total_value"]), tuple(rows))
    if valuation.to_dict() != data:
        raise ValueError("exact valuation display or canonical values mismatch")
    return valuation


def _context(value: Any) -> PortfolioResearchContextEvidence:
    names = {field.name for field in fields(PortfolioAllocationContextRow)}
    data = _object(value, names | {"account_kind", "portfolio_id", "snapshot_id", "available_at", "source_hash", "health_known"})
    identity = {name: data.pop(name) for name in ("account_kind", "portfolio_id", "snapshot_id", "available_at", "source_hash", "health_known")}
    for name in ("stock_code", "stock_name", "health_state"):
        data[name] = _string(data[name])
    for name in ("sector_id", "market_data_as_of_date"):
        if data[name] is not None:
            data[name] = _string(data[name])
    data["hard_risk_reasons"] = _strings(data["hard_risk_reasons"])
    if data["reference_price"] is not None:
        data["reference_price"] = _money(data["reference_price"])
    identity["available_at"] = _clock(identity["available_at"])
    for name in ("account_kind", "portfolio_id", "snapshot_id", "source_hash"):
        identity[name] = _string(identity[name])
    return PortfolioResearchContextEvidence(context=PortfolioAllocationContextRow(**data), **identity)


def _request(value: Any) -> PortfolioResearchScenarioRequest:
    data = _object(value, {field.name for field in fields(PortfolioResearchScenarioRequest)})
    for name in ("account_kind", "portfolio_id", "snapshot_id", "research_source_hash"):
        data[name] = _string(data[name])
    data["decision_at"] = _clock(data["decision_at"])
    data["candidate_symbols"] = _strings(data["candidate_symbols"])
    data["contexts"] = tuple(_context(item) for item in _list(data["contexts"]))
    if data["explicit_weights"] is not None:
        data["explicit_weights"] = _weights(data["explicit_weights"])
    return PortfolioResearchScenarioRequest(**data)


def _row(value: Any) -> PortfolioAllocationRowV2:
    data = _object(value, {field.name for field in fields(PortfolioAllocationRowV2)})
    for name in ("stock_code", "stock_name"):
        data[name] = _string(data[name])
    for name in ("executable_amount", "estimated_cost"):
        data[name] = _money(data[name])
    if data["reference_price"] is not None:
        data["reference_price"] = _money(data["reference_price"])
    data["diagnostics"] = _strings(data["diagnostics"])
    return PortfolioAllocationRowV2(**data)


def _projection(value: Any) -> PortfolioAllocationProjectionV1:
    data = _object(value, {field.name for field in fields(PortfolioAllocationProjectionV1)})
    data["target_weights"] = _weights(data["target_weights"])
    if data["executable_weights"] is not None:
        data["executable_weights"] = _weights(data["executable_weights"])
    data["rows"] = tuple(_row(item) for item in _list(data["rows"]))
    for name in ("post_cost_cash_amount", "total_estimated_cost"):
        data[name] = _money(data[name])
    data["advice_action"] = _string(data["advice_action"])
    data["reasons"] = _strings(data["reasons"])
    return PortfolioAllocationProjectionV1(**data)


def _research_flags(data: dict[str, Any]) -> None:
    if data.pop("research_only") is not True or data.pop("broker_order_allowed") is not False or data.pop("apply_rebalance") is not False:
        raise ValueError("scenario artifact cannot authorize execution")


def _result(value: Any) -> PortfolioRuleAllocationResultV1:
    data = _object(value, {field.name for field in fields(PortfolioRuleAllocationResultV1)} | {
        "schema", "research_only", "broker_order_allowed", "apply_rebalance",
    })
    if data.pop("schema") != "portfolio-rule-allocation.v1":
        raise ValueError("unsupported scenario allocation schema")
    _research_flags(data)
    data["requested_weights"] = _weights(data["requested_weights"])
    data["projection"] = _projection(data["projection"])
    for name in ("decision_date", "source_hash", "rule_policy_hash", "allocation_policy_hash"):
        data[name] = _string(data[name])
    if data["causal_portfolio_state_hash"] is not None:
        data["causal_portfolio_state_hash"] = _string(data["causal_portfolio_state_hash"])
    return PortfolioRuleAllocationResultV1(**data)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("scenario artifact duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value: str) -> Any:
    raise ValueError("scenario artifact rejects float or non-finite JSON number")


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 18:
        raise ValueError("scenario artifact integer exceeds limit")
    return int(value)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def scenario_artifact_id(payload: bytes) -> str:
    if type(payload) is not bytes or len(payload) > MAX_SCENARIO_BYTES:
        raise ValueError("scenario artifact payload size or type rejected")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def decode_scenario_artifact(payload: bytes) -> PortfolioResearchScenarioComparison:
    scenario_artifact_id(payload)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_reject_number,
                           parse_constant=_reject_number, parse_int=_integer)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("scenario artifact invalid JSON") from exc
    data = _object(value, {field.name for field in fields(PortfolioResearchScenarioComparison)} | {
        "schema", "research_only", "broker_order_allowed", "apply_rebalance",
    })
    if data.pop("schema") != "portfolio-research-scenarios.v3":
        raise ValueError("unsupported scenario artifact schema")
    _research_flags(data)
    data["account"] = _account(data["account"])
    data["request"] = _request(data["request"])
    data["decision_at"] = _clock(data["decision_at"])
    for name in ("research_source_hash", "input_hash"):
        data[name] = _string(data[name])
    scenarios = []
    for item in _list(data["scenarios"]):
        scenario = _object(item, {"scenario_kind", "result"})
        scenarios.append(PortfolioResearchScenario(_string(scenario["scenario_kind"]), _result(scenario["result"])))
    data["scenarios"] = tuple(scenarios)
    comparison = PortfolioResearchScenarioComparison(**data)
    if _canonical(comparison.to_dict()) != payload:
        raise ValueError("scenario artifact is not canonical or normalized facts differ")
    return comparison


def encode_scenario_artifact(comparison: PortfolioResearchScenarioComparison) -> bytes:
    if not isinstance(comparison, PortfolioResearchScenarioComparison):
        raise ValueError("scenario artifact requires typed comparison")
    payload = _canonical(comparison.to_dict())
    decode_scenario_artifact(payload)
    return payload
