from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract, CausalPortfolioState, MLAllocationProposal,
    PortfolioAllocationContextRow, PortfolioAllocationRequestV2,
    PortfolioRuleAllocationRequestV1,
)
from app_module.portfolio_allocation_service import PortfolioAllocationService
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState, PortfolioResearchContextEvidence,
    PortfolioResearchPosition, PortfolioResearchScenarioRequest,
    PortfolioResearchScenarioService,
)


HASH = "sha256:" + "a" * 64
AVAILABLE = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
DECISION = datetime(2026, 10, 9, 1, tzinfo=timezone.utc)


class ExactReader:
    def __init__(self, state: PortfolioResearchAccountState) -> None:
        self.state = state
        self.calls: list[tuple[str, str, str]] = []

    def read_exact(self, *, account_kind: str, portfolio_id: str, snapshot_id: str) -> PortfolioResearchAccountState:
        self.calls.append((account_kind, portfolio_id, snapshot_id))
        return self.state


def _state(*, kind: str = "paper", account_id: str = "paper-a") -> PortfolioResearchAccountState:
    return PortfolioResearchAccountState(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a",
        as_of_date="2026-10-08", available_at=AVAILABLE, source_hash=HASH,
        capital_amount=Decimal("1000000.00"),
        current_weights=AllocationWeightContract({"2330": 1000}, 9000),
        positions=(PortfolioResearchPosition("2330", 1000),),
        valuation=PortfolioResearchValuation(Decimal("900000.00"), Decimal("1000000.00"), (
            PortfolioResearchValuedPosition("2330", 1000, Decimal("100.00"), Decimal("100000.00")),
        )),
    )


def _evidence(symbol: str, *, kind: str = "paper", account_id: str = "paper-a") -> PortfolioResearchContextEvidence:
    return PortfolioResearchContextEvidence(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a", source_hash=HASH,
        available_at=AVAILABLE, health_known=True,
        context=PortfolioAllocationContextRow(
            stock_code=symbol, current_weight_bp=1000 if symbol == "2330" else 0,
            current_shares=1000 if symbol == "2330" else 0,
            sector_id="sector-" + symbol, health_state="HEALTHY",
            reference_price=Decimal("100.00"), median_volume_20d_shares=200000,
            market_data_as_of_date="2026-10-08", trading_days_since_last_trade=5,
        ),
    )


def _request(*, kind: str = "paper", account_id: str = "paper-a") -> PortfolioResearchScenarioRequest:
    return PortfolioResearchScenarioRequest(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a",
        decision_at=DECISION, candidate_symbols=("2330", "2382", "2454"),
        contexts=tuple(_evidence(symbol, kind=kind, account_id=account_id) for symbol in ("2330", "2382", "2454")),
        research_source_hash=HASH,
        explicit_weights=AllocationWeightContract({"2330": 1500, "2382": 1000}, 7500),
    )


def test_compare_preserves_account_current_and_human_targets_with_risk_limits() -> None:
    state = _state()
    reader = ExactReader(state)
    result = PortfolioResearchScenarioService(reader).compare(_request())
    assert reader.calls == [("paper", "paper-a", "snapshot-a")]
    assert [scenario.scenario_kind for scenario in result.scenarios] == ["maintain", "equal_weight", "explicit_target"]
    maintain, equal, explicit = [scenario.result for scenario in result.scenarios]
    assert maintain.requested_weights == state.current_weights
    assert equal.requested_weights.symbol_weights_bp == {"2330": 3334, "2382": 3333, "2454": 3333}
    assert equal.projection.target_weights.symbol_weights_bp == {"2330": 1500, "2382": 1500, "2454": 1500}
    assert explicit.requested_weights == _request().explicit_weights
    assert equal.projection.total_estimated_cost > Decimal("0")
    assert equal.projection.post_cost_cash_amount >= Decimal("200000")
    assert "single_position_cap_applied" in equal.projection.reasons
    payload = result.to_dict()
    assert payload["broker_order_allowed"] is False
    assert payload["apply_rebalance"] is False
    assert "model_hash" not in equal.to_dict()
    assert state.current_weights.symbol_weights_bp == {"2330": 1000}


@pytest.mark.parametrize("kind", ["manual", "user_declared", "paper"])
def test_same_stock_is_bound_to_selected_account_kind(kind: str) -> None:
    reader = ExactReader(_state(kind=kind, account_id="account-" + kind))
    request = _request(kind=kind, account_id="account-" + kind)
    result = PortfolioResearchScenarioService(reader).compare(request)
    assert result.account.account_kind == kind
    assert reader.calls == [(kind, "account-" + kind, "snapshot-a")]
    with pytest.raises(ValueError, match="identity mismatch"):
        PortfolioResearchScenarioService(reader).compare(replace(request, portfolio_id="other"))


@pytest.mark.parametrize("change, message", [
    ({"as_of_date": "2026-10-09"}, "strictly before"),
    ({"as_of_date": "2026-10-10"}, "strictly before"),
    ({"available_at": datetime(2026, 10, 10, tzinfo=timezone.utc)}, "strictly before"),
    ({"snapshot_id": "wrong"}, "identity mismatch"),
])
def test_snapshot_date_clock_and_identity_are_checked(change: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PortfolioResearchScenarioService(ExactReader(replace(_state(), **change))).compare(_request())


@pytest.mark.parametrize("mutation, message", [
    ({"portfolio_id": "other"}, "another account"),
    ({"account_kind": "manual"}, "another account"),
    ({"snapshot_id": "snapshot-b"}, "another account snapshot"),
    ({"available_at": datetime(2026, 10, 10, tzinfo=timezone.utc)}, "after decision"),
    ({"health_known": False}, "unknown is not healthy"),
])
def test_context_identity_availability_and_unknown_health_fail_closed(mutation: dict, message: str) -> None:
    request = _request()
    evidence = replace(request.contexts[0], **mutation)
    with pytest.raises(ValueError, match=message):
        PortfolioResearchScenarioService(ExactReader(_state())).compare(replace(request, contexts=(evidence, *request.contexts[1:])))


@pytest.mark.parametrize("mutation, message", [
    ({"current_weight_bp": None}, "current weight"),
    ({"current_weight_bp": 0}, "current weight"),
    ({"current_shares": 0}, "shares differ"),
    ({"market_data_as_of_date": "2026-10-09"}, "not strictly prior"),
])
def test_current_state_and_market_clock_cannot_be_silently_replaced(mutation: dict, message: str) -> None:
    request = _request()
    evidence = replace(request.contexts[0], context=replace(request.contexts[0].context, **mutation))
    with pytest.raises(ValueError, match=message):
        PortfolioResearchScenarioService(ExactReader(_state())).compare(replace(request, contexts=(evidence, *request.contexts[1:])))


def test_full_account_universe_and_selected_candidates_are_required() -> None:
    request = _request()
    service = PortfolioResearchScenarioService(ExactReader(_state()))
    with pytest.raises(ValueError, match="context universe"):
        service.compare(replace(request, contexts=request.contexts[1:]))
    with pytest.raises(ValueError, match="unselected symbol"):
        service.compare(replace(request, explicit_weights=AllocationWeightContract({"9999": 1500}, 8500)))
    with pytest.raises(ValueError, match="complete valued quantity universe"):
        replace(_state(), positions=())
    with pytest.raises(ValueError, match="duplicate candidate"):
        replace(request, candidate_symbols=("2330", "2330"))


def test_unknown_price_does_not_reweight_equal_candidates() -> None:
    request = _request()
    evidence = replace(request.contexts[1], context=replace(request.contexts[1].context, reference_price=None))
    with pytest.raises(ValueError, match="exact price for each"):
        PortfolioResearchScenarioService(ExactReader(_state())).compare(replace(request, contexts=(request.contexts[0], evidence, request.contexts[2])))


def test_liquidity_cooldown_and_turnover_use_existing_allocation_controls() -> None:
    request = _request()
    contexts = list(request.contexts)
    contexts[1] = replace(contexts[1], context=replace(contexts[1].context, median_volume_20d_shares=1000))
    contexts[2] = replace(contexts[2], context=replace(contexts[2].context, trading_days_since_last_trade=0))
    result = PortfolioResearchScenarioService(ExactReader(_state())).compare(replace(request, contexts=tuple(contexts), weekly_turnover_used_bp=2000))
    projection = result.scenarios[1].result.projection
    assert projection.executable_weights == _state().current_weights
    assert projection.total_estimated_cost == Decimal("0.00")
    assert "liquidity_5pct_participation_cap_applied" in projection.reasons
    assert "same_symbol_cooldown_active" in projection.reasons
    assert "weekly_turnover_cap_exceeded" in projection.reasons


def test_research_hash_freezes_prices_policy_and_account_but_not_candidate_order() -> None:
    service = PortfolioResearchScenarioService(ExactReader(_state()))
    request = _request()
    result = service.compare(request)
    assert result.to_dict() == service.compare(replace(request, candidate_symbols=tuple(reversed(request.candidate_symbols)), contexts=tuple(reversed(request.contexts)))).to_dict()
    evidence = replace(request.contexts[1], context=replace(request.contexts[1].context, reference_price=Decimal("101")))
    assert result.input_hash != service.compare(replace(request, contexts=(request.contexts[0], evidence, request.contexts[2]))).input_hash
    other = PortfolioResearchScenarioService(ExactReader(_state(account_id="other"))).compare(_request(account_id="other"))
    assert result.input_hash != other.input_hash


def test_same_account_unchanged_positions_still_require_exact_context_snapshot() -> None:
    request = _request()
    state = replace(_state(), snapshot_id="snapshot-b")
    request_b = replace(request, snapshot_id="snapshot-b")
    service = PortfolioResearchScenarioService(ExactReader(state))
    with pytest.raises(ValueError, match="another account snapshot"):
        service.compare(request_b)
    coupled = replace(request_b, contexts=tuple(
        replace(evidence, snapshot_id="snapshot-b") for evidence in request.contexts
    ))
    result_b = service.compare(coupled)
    result_a = PortfolioResearchScenarioService(ExactReader(_state())).compare(request)
    assert result_a.input_hash != result_b.input_hash
    assert result_b.request.to_dict()["contexts"][0]["snapshot_id"] == "snapshot-b"
    assert result_b.to_dict()["schema"] == "portfolio-research-scenarios.v3"


@pytest.mark.parametrize("snapshot_id", ["", " snapshot-a "])
def test_context_snapshot_identity_must_be_explicit_and_canonical(snapshot_id: str) -> None:
    with pytest.raises(ValueError):
        replace(_evidence("2330"), snapshot_id=snapshot_id)


def test_taipei_decision_day_uses_aware_clock_and_rejects_naive_datetime() -> None:
    request = replace(_request(), decision_at=datetime(2026, 10, 8, 17, tzinfo=timezone.utc))
    result = PortfolioResearchScenarioService(ExactReader(_state())).compare(request)
    assert result.scenarios[0].result.decision_date == "2026-10-09"
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(request, decision_at=datetime(2026, 10, 9))


def test_rule_entry_matches_legacy_zero_alpha_numerical_projection() -> None:
    service = PortfolioAllocationService()
    state = _state()
    weights = AllocationWeightContract({"2330": 1500, "2382": 1500}, 7000)
    contexts = tuple(_evidence(symbol).context for symbol in ("2330", "2382"))
    causal = CausalPortfolioState.create(as_of_date=state.as_of_date, current_weights=state.current_weights)
    rule = service.project_rule_only(PortfolioRuleAllocationRequestV1(
        decision_date="2026-10-09", capital_amount=state.capital_amount,
        rule_requested_weights=weights, contexts=contexts, current_cash_bp=9000,
        source_hash=HASH, rule_policy_hash=HASH, causal_portfolio_state=causal,
    ))
    ml = MLAllocationProposal(
        decision_date="2026-10-09", model_id="fixture", dataset_id="fixture", universe_id="fixture",
        policy_id="fixture", requested_weights=AllocationWeightContract.cash_only(),
        model_hash=HASH, dataset_identity_hash=HASH, dataset_manifest_file_hash=HASH,
        universe_hash=HASH, policy_hash=HASH, coverage_bp=10000,
    )
    old = service.project(PortfolioAllocationRequestV2(
        decision_date="2026-10-09", capital_amount=state.capital_amount,
        rule_requested_weights=weights, ml_proposal=ml, alpha_bp=0,
        contexts=contexts, current_cash_bp=9000, rule_policy_hash=HASH, causal_portfolio_state=causal,
    ))
    assert rule.projection.rows == old.rows
    assert rule.projection.target_weights == old.target_weights
    assert rule.projection.executable_weights == old.executable_weights
    assert rule.projection.total_estimated_cost == old.total_estimated_cost
    assert rule.projection.post_cost_cash_amount == old.post_cost_cash_amount


def test_rule_request_rejects_float_and_missing_current_state_keeps_execution_unknown() -> None:
    request = PortfolioRuleAllocationRequestV1(
        decision_date="2026-10-09", capital_amount=Decimal("1000000"),
        rule_requested_weights=AllocationWeightContract({"2330": 1500}, 8500),
        contexts=(_evidence("2330").context,), current_cash_bp=9000,
        source_hash=HASH, rule_policy_hash=HASH,
    )
    with pytest.raises(ValueError, match="must be Decimal"):
        replace(request, capital_amount=1000000.0)
    result = PortfolioAllocationService().project_rule_only(request)
    assert result.projection.executable_weights is None
    assert all(row.executable_shares is None for row in result.projection.rows)
    assert "current_portfolio_state_incomplete_no_execution" in result.projection.reasons
