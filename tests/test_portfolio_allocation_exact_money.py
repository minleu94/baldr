"""實際現金與完整股數進入既有配置引擎的因果／風控回歸。"""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract, CausalPortfolioState, PortfolioAllocationContextRow,
    PortfolioRuleAllocationRequestV1,
)
from app_module.portfolio_allocation_service import PortfolioAllocationService
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig


HASH = "sha256:" + "a" * 64


def _valuation():
    return PortfolioResearchValuation(Decimal("900000.37"), Decimal("1000000.37"), (
        PortfolioResearchValuedPosition("2330", 1000, Decimal("100.00"), Decimal("100000.00")),
    ))


def _request(valuation=None, *, health="HEALTHY"):
    valuation = valuation or _valuation()
    causal = CausalPortfolioState.create_valued(as_of_date="2026-10-08", valuation=valuation)
    contexts = tuple(PortfolioAllocationContextRow(
        stock_code=row.stock_code, current_weight_bp=causal.current_weights.weight_for(row.stock_code),
        current_shares=row.quantity, reference_price=row.mark_price, sector_id="sector-" + row.stock_code,
        health_state=health, median_volume_20d_shares=1000000,
        market_data_as_of_date="2026-10-08", trading_days_since_last_trade=5,
    ) for row in valuation.positions)
    return PortfolioRuleAllocationRequestV1(
        decision_date="2026-10-09", capital_amount=valuation.total_value,
        rule_requested_weights=causal.current_weights, contexts=contexts,
        current_cash_bp=causal.current_weights.cash_weight_bp,
        source_hash=HASH, rule_policy_hash=HASH, causal_portfolio_state=causal,
    )


def test_maintain_preserves_exact_cash_and_all_position_amounts():
    request = _request()
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights == request.causal_portfolio_state.current_weights
    assert projection.post_cost_cash_amount == Decimal("900000.37")
    assert projection.rows[0].executable_shares == 1000
    assert projection.rows[0].executable_amount == Decimal("100000.00")
    assert projection.total_estimated_cost == Decimal("0.00")
    assert projection.post_cost_cash_amount != PortfolioAllocationService._amount_from_bp(request.capital_amount, request.current_cash_bp)


def test_causal_v2_hash_preserves_tiny_position_and_exact_money():
    first = _request().causal_portfolio_state
    other = replace(_valuation(), cash_amount=Decimal("900000.38"), total_value=Decimal("1000000.38"))
    second = CausalPortfolioState.create_valued(as_of_date="2026-10-08", valuation=other)
    assert first.current_weights == second.current_weights
    assert first.state_hash != second.state_hash
    assert first.to_dict()["schema_version"] == "causal-portfolio-state.v2"
    tiny = PortfolioResearchValuation(Decimal("999999.99"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("9999", 1, Decimal("0.01"), Decimal("0.01")),
    ))
    causal = CausalPortfolioState.create_valued(as_of_date="2026-10-08", valuation=tiny)
    assert causal.complete_symbol_universe == ("9999",)
    assert causal.current_weights.symbol_weights_bp == {"9999": 0}
    projection = PortfolioAllocationService().project_rule_only(_request(tiny)).projection
    assert projection.executable_weights.symbol_weights_bp == {"9999": 0}
    assert projection.rows[0].executable_shares == 1
    assert projection.rows[0].executable_amount == Decimal("0.01")
    assert projection.advice_action == "HOLD"


def test_cash_budget_never_recovers_from_display_weight():
    request = _request()
    with pytest.raises(ValueError, match="capital differs"):
        PortfolioAllocationService().project_rule_only(replace(request, capital_amount=Decimal("1000000.38")))


@pytest.mark.parametrize("mutation", [{"current_shares": 999}, {"reference_price": Decimal("101")}])
def test_context_must_match_exact_quantity_and_valuation_price(mutation):
    request = _request()
    changed = replace(request, contexts=(replace(request.contexts[0], **mutation),))
    projection = PortfolioAllocationService().project_rule_only(changed).projection
    assert projection.executable_weights is None
    assert projection.post_cost_cash_amount == _valuation().cash_amount
    assert "causal_portfolio_context_valuation_mismatch" in projection.reasons


def test_actual_position_count_includes_every_positive_quantity_even_at_zero_bp():
    rows = tuple(PortfolioResearchValuedPosition(str(1000 + index), 1, Decimal("0.01"), Decimal("0.01")) for index in range(9))
    valuation = PortfolioResearchValuation(Decimal("999999.91"), Decimal("1000000.00"), rows)
    projection = PortfolioAllocationService().project_rule_only(_request(valuation)).projection
    assert len(projection.rows) == 9
    assert projection.executable_weights is None
    assert "hard_constraint_position_count_violated" in projection.reasons


def test_zero_bp_odd_lot_does_not_fake_exit_completion():
    valuation = PortfolioResearchValuation(Decimal("999999.99"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("9999", 1, Decimal("0.01"), Decimal("0.01")),
    ))
    request = replace(_request(valuation, health="EXIT_CANDIDATE"), rule_requested_weights=AllocationWeightContract.cash_only())
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is None
    assert "sell_below_lot_size" in projection.reasons
    assert "hard_constraint_exit_quantity_nonzero:9999" in projection.reasons
    assert projection.advice_action == "EXIT_CANDIDATE"


def test_zero_bp_board_lot_hard_exit_uses_complete_amount_and_quantity():
    valuation = PortfolioResearchValuation(Decimal("999990.00"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("9999", 1000, Decimal("0.01"), Decimal("10.00")),
    ))
    request = replace(_request(valuation, health="EXIT_CANDIDATE"), rule_requested_weights=AllocationWeightContract.cash_only())
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights == AllocationWeightContract.cash_only()
    assert projection.rows[0].executable_shares == 0
    assert projection.post_cost_cash_amount == Decimal("999999.94")
    assert projection.total_estimated_cost == Decimal("0.06")
    assert projection.advice_action == "EXIT_CANDIDATE"


def test_legacy_causal_payload_remains_exactly_v1_without_money_fields():
    legacy = CausalPortfolioState.create(as_of_date="2026-10-08", current_weights=AllocationWeightContract({"2330": 1000}, 9000))
    assert legacy.to_dict()["schema_version"] == "causal-portfolio-state.v1"
    assert "valuation" not in legacy.to_dict()


def _with_candidate(request, code="2382", *, price="100.00", weight=1000):
    context = PortfolioAllocationContextRow(
        stock_code=code, current_weight_bp=0, current_shares=0,
        reference_price=Decimal(price), sector_id="sector-" + code,
        health_state="HEALTHY", median_volume_20d_shares=1000000,
        market_data_as_of_date="2026-10-08", trading_days_since_last_trade=5,
    )
    weights = dict(request.rule_requested_weights.symbol_weights_bp)
    weights[code] = weight
    return replace(request, contexts=(*request.contexts, context),
        rule_requested_weights=AllocationWeightContract(weights, 10000 - sum(weights.values())))


def test_buy_cost_and_complete_post_trade_money_conserve_nav():
    request = _with_candidate(_request())
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is not None
    rows = {row.stock_code: row for row in projection.rows}
    assert rows["2382"].executable_shares == 1000
    assert rows["2382"].estimated_cost == Decimal("250.00")
    assert projection.post_cost_cash_amount == Decimal("799750.37")
    assert sum((row.executable_amount for row in projection.rows), projection.post_cost_cash_amount) == request.capital_amount - projection.total_estimated_cost


def test_hard_exit_proceeds_fund_buy_with_both_costs_and_watch_quantity_unchanged():
    request = _with_candidate(_request(health="EXIT_CANDIDATE"))
    request = replace(request, rule_requested_weights=AllocationWeightContract({"2382": 1000}, 9000))
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is not None
    rows = {row.stock_code: row for row in projection.rows}
    assert rows["2330"].executable_shares == 0
    assert rows["2382"].executable_shares == 1000
    assert rows["2330"].estimated_cost == Decimal("550.00")
    assert projection.total_estimated_cost == Decimal("800.00")
    assert projection.post_cost_cash_amount == Decimal("899200.37")
    assert sum((row.executable_amount for row in projection.rows), projection.post_cost_cash_amount) == request.capital_amount - projection.total_estimated_cost

    watch = _with_candidate(_request(health="WATCH"))
    after = PortfolioAllocationService().project_rule_only(watch).projection
    assert after.executable_weights is not None
    held = next(row for row in after.rows if row.stock_code == "2330")
    assert held.executable_shares == 1000
    assert held.executable_weight_bp >= held.current_weight_bp
    assert "hard_constraint_health_add_prohibited:2330" not in after.reasons


@pytest.mark.parametrize("date", ["2026-10-09", "2026-10-10"])
def test_valued_state_same_day_or_future_never_grants_execution(date):
    request = _request()
    causal = CausalPortfolioState.create_valued(as_of_date=date, valuation=_valuation())
    projection = PortfolioAllocationService().project_rule_only(replace(request, causal_portfolio_state=causal)).projection
    assert projection.executable_weights is None
    assert "causal_portfolio_state_not_strictly_prior" in projection.reasons
    assert projection.post_cost_cash_amount == _valuation().cash_amount


def test_same_day_candidate_quote_is_not_used_to_buy():
    request = _with_candidate(_request())
    request = replace(request, contexts=(request.contexts[0], replace(request.contexts[1], market_data_as_of_date=request.decision_date)))
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is not None
    assert next(row for row in projection.rows if row.stock_code == "2382").executable_shares == 0
    assert "pit_market_data_unavailable_no_new_position" in projection.reasons
    assert projection.post_cost_cash_amount == _valuation().cash_amount


def test_unknown_sector_on_actual_held_position_cannot_grant_safe_projection():
    request = _request()
    projection = PortfolioAllocationService().project_rule_only(replace(request, contexts=(replace(request.contexts[0], sector_id=None),))).projection
    assert projection.executable_weights is None
    assert "hard_constraint_exact_sector_unknown:2330" in projection.reasons


def test_actual_single_cap_rejects_amount_hidden_by_rounded_display_bp():
    valuation = PortfolioResearchValuation(Decimal("849999.99"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("2330", 1000, Decimal("150.00001"), Decimal("150000.01")),
    ))
    request = _request(valuation)
    assert request.current_cash_bp == 8500
    assert request.contexts[0].current_weight_bp == 1500
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is None
    assert "hard_constraint_single_position_cap_violated" in projection.reasons


def test_actual_sector_cap_rejects_combined_amount_hidden_by_display_bp():
    valuation = PortfolioResearchValuation(Decimal("699999.98"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("2330", 1000, Decimal("150.00001"), Decimal("150000.01")),
        PortfolioResearchValuedPosition("2382", 1000, Decimal("150.00001"), Decimal("150000.01")),
    ))
    request = _request(valuation)
    request = replace(request, contexts=tuple(replace(row, sector_id="same-sector") for row in request.contexts))
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is None
    assert "hard_constraint_sector_cap_violated" in projection.reasons


def test_actual_cash_floor_rejects_fraction_hidden_by_rounded_cash_bp():
    rows = tuple(PortfolioResearchValuedPosition(str(1000 + index), 1000, Decimal("100.00001") if index == 0 else Decimal("100"), Decimal("100000.01") if index == 0 else Decimal("100000.00")) for index in range(8))
    valuation = PortfolioResearchValuation(Decimal("199999.99"), Decimal("1000000.00"), rows)
    request = _request(valuation)
    assert request.current_cash_bp == 2000
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is None
    assert "hard_constraint_exact_cash_floor_violated" in projection.reasons


def test_exact_cash_residual_can_fund_lot_that_display_bp_cannot_fund():
    rows = (PortfolioResearchValuedPosition("1000", 344827586, Decimal("0.00029"), Decimal("100000.00")), *tuple(
        PortfolioResearchValuedPosition(str(1000 + index), 1000, Decimal("100"), Decimal("100000.00")) for index in range(1, 8)))
    valuation = PortfolioResearchValuation(Decimal("200000.37"), Decimal("1000000.37"), rows)
    request = _request(valuation)
    weights = dict(request.rule_requested_weights.symbol_weights_bp)
    weights["1000"] = 1500
    request = replace(request, rule_requested_weights=AllocationWeightContract(weights, 10000 - sum(weights.values())),
        contexts=tuple(replace(row, median_volume_20d_shares=10**12) if row.stock_code == "1000" else row for row in request.contexts))
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.executable_weights is not None
    first = next(row for row in projection.rows if row.stock_code == "1000")
    assert first.executable_shares == 344828586
    assert projection.post_cost_cash_amount == Decimal("200000.08")
    assert first.estimated_cost == Decimal("0.00")
    assert PortfolioAllocationService._amount_from_bp(request.capital_amount, request.current_cash_bp) == Decimal("200000.07")


def test_costs_raise_actual_exposure_above_cap_and_discard_projection():
    valuation = PortfolioResearchValuation(Decimal("850000.00"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("2330", 1000, Decimal("150"), Decimal("150000.00")),
    ))
    projection = PortfolioAllocationService().project_rule_only(_with_candidate(_request(valuation))).projection
    assert projection.executable_weights is None
    assert "hard_constraint_single_position_cap_violated" in projection.reasons
    assert projection.post_cost_cash_amount == valuation.cash_amount
    assert projection.total_estimated_cost == Decimal("0.00")


def test_policy_identity_changes_with_exact_projection_method_and_parameters():
    first = PortfolioAllocationService()
    altered = PortfolioAllocationService(PaperPortfolioPolicyConfig(minimum_cash_bp=2500))
    assert first.allocation_policy_hash != altered.allocation_policy_hash
    assert len(first.allocation_policy_hash) == 71


def test_exact_projection_is_independent_of_caller_decimal_precision_and_exponent():
    request = _with_candidate(_request())
    expected = PortfolioAllocationService().project_rule_only(request)
    with localcontext() as context:
        context.prec = 4
        context.Emax = 4
        context.Emin = -4
        actual = PortfolioAllocationService().project_rule_only(request)
    assert actual == expected


def test_cash_only_target_keeps_tiny_holding_visible_under_existing_rebalance_controls():
    valuation = PortfolioResearchValuation(Decimal("999990.00"), Decimal("1000000.00"), (
        PortfolioResearchValuedPosition("9999", 1000, Decimal("0.01"), Decimal("10.00")),
    ))
    request = replace(_request(valuation), rule_requested_weights=AllocationWeightContract.cash_only())
    projection = PortfolioAllocationService().project_rule_only(request).projection
    assert projection.target_weights == AllocationWeightContract.cash_only()
    assert projection.executable_weights != AllocationWeightContract.cash_only()
    assert projection.executable_weights.symbol_weights_bp == {"9999": 0}
    assert projection.rows[0].executable_shares == 1000
    assert projection.rows[0].executable_amount == Decimal("10.00")
    assert projection.advice_action == "HOLD"
    assert "zero_bp_position_retained_by_rebalance_controls" in projection.reasons
