from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from app_module.paper_portfolio_snapshot_repository import PaperPortfolioPositionSnapshot, PaperPortfolioSnapshot
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition


def _position(code="2330", quantity=1000, price="100.00", value="100000.00"):
    return PortfolioResearchValuedPosition(code, quantity, Decimal(price), Decimal(value))


def test_exact_cash_and_tiny_positive_position_survive_zero_display_bp():
    tiny = _position("9999", 1, "0.01", "0.01")
    state = PortfolioResearchValuation(Decimal("999999.99"), Decimal("1000000.00"), (tiny,))
    assert state.positions == (tiny,)
    assert state.display_weights.symbol_weights_bp == {"9999": 0}
    assert state.display_weights.cash_weight_bp == 10000
    assert state.cash_amount != state.total_value
    assert state.to_dict()["cash_amount"] == "999999.99"
    assert state.to_dict()["positions"][0]["quantity"] == 1


def test_largest_remainder_is_canonical_and_isolated_from_decimal_precision():
    positions = tuple(_position(code, 1, "1", "1") for code in ("2454", "2330", "2382"))
    state = PortfolioResearchValuation(Decimal("1"), Decimal("4"), positions)
    assert tuple(row.stock_code for row in state.positions) == ("2330", "2382", "2454")
    assert state.display_weights.symbol_weights_bp == {"2330": 2500, "2382": 2500, "2454": 2500}
    thirds = PortfolioResearchValuation(Decimal("1.00"), Decimal("3.00"), positions[:2])
    assert thirds.display_weights.symbol_weights_bp == {"2330": 3334, "2454": 3333}
    assert thirds.display_weights.cash_weight_bp == 3333
    with localcontext() as context:
        context.prec = 3
        context.Emax = 3
        assert state.to_dict() == replace(state, positions=tuple(reversed(state.positions))).to_dict()
        assert thirds.display_weights.cash_weight_bp == 3333
        assert _position(price="123.4567", value="123456.70").market_value == Decimal("123456.70")


def test_hash_binds_exact_cash_even_when_display_bp_unchanged():
    first = PortfolioResearchValuation(Decimal("999999.99"), Decimal("1000000"), (_position("9999", 1, "0.01", "0.01"),))
    second = PortfolioResearchValuation(Decimal("999999.98"), Decimal("1000000"), (_position("9999", 1, "0.02", "0.02"),))
    assert first.display_weights == second.display_weights
    assert first.valuation_hash != second.valuation_hash
    assert first.valuation_hash == replace(first, cash_amount=Decimal("999999.9900")).valuation_hash


@pytest.mark.parametrize("change", [
    {"quantity": True}, {"quantity": 0}, {"quantity": -1}, {"quantity": 10**12 + 1},
    {"mark_price": 100.0}, {"mark_price": Decimal("NaN")}, {"mark_price": Decimal("Infinity")},
    {"mark_price": Decimal("0")}, {"mark_price": Decimal("1E-100000")},
    {"market_value": Decimal("99999.99")}, {"market_value": Decimal("100000.001")},
    {"market_value": Decimal("1E+100000")}, {"stock_code": " 2330 "}, {"stock_code": "CASH"},
])
def test_incomplete_or_inexact_position_fails_closed(change):
    with pytest.raises(ValueError):
        replace(_position(), **change)


@pytest.mark.parametrize("cash,nav,positions", [
    (Decimal("900000"), Decimal("999999.99"), (_position(),)),
    (Decimal("0"), Decimal("0"), ()),
    (Decimal("1.001"), Decimal("1.001"), ()),
    (Decimal("-1"), Decimal("1"), ()),
    (1.0, Decimal("1"), ()),
    (Decimal("1E+100000"), Decimal("1E+100000"), ()),
    (Decimal("1E-100000"), Decimal("1"), ()),
    (Decimal("0"), Decimal("200000"), (_position(), _position())),
    (Decimal("900000"), Decimal("1000000"), [_position()]),
])
def test_incomplete_or_nonconserving_state_fails_closed(cash, nav, positions):
    with pytest.raises(ValueError):
        PortfolioResearchValuation(cash, nav, positions)


def _snapshot():
    return PaperPortfolioSnapshot("snapshot-a", "paper-a", "2026-10-08", "result-a",
        Decimal("900000.00"), Decimal("1000000.00"),
        (PaperPortfolioPositionSnapshot("2330", 1000, Decimal("100"), Decimal("100000"), 1000),))


def test_snapshot_conversion_validates_real_units_and_keeps_tiny_holdings():
    source = _snapshot()
    valuation = PortfolioResearchValuation.from_snapshot(source)
    assert valuation.cash_amount == source.cash
    assert valuation.total_value == source.total_value
    assert valuation.positions[0].quantity == 1000
    tiny = replace(source, cash=Decimal("999999.99"), positions=(
        PaperPortfolioPositionSnapshot("9999", 1, Decimal("0.01"), Decimal("0.01"), 0),))
    assert PortfolioResearchValuation.from_snapshot(tiny).positions[0].quantity == 1


@pytest.mark.parametrize("mutation", [
    {"weight_bp": 999}, {"market_value": Decimal("99999.99")}, {"quantity": 0},
])
def test_snapshot_conversion_refuses_corrupt_complete_facts(mutation):
    source = _snapshot()
    with pytest.raises(ValueError):
        PortfolioResearchValuation.from_snapshot(replace(source, positions=(replace(source.positions[0], **mutation),)))


def test_snapshot_conversion_refuses_unknown_row_type_without_silently_dropping_it():
    with pytest.raises(ValueError, match="complete tuple"):
        PortfolioResearchValuation.from_snapshot(replace(_snapshot(), positions=("unknown",)))


def test_position_count_bound_is_checked_before_snapshot_conversion():
    source = _snapshot()
    with pytest.raises(ValueError, match="complete tuple"):
        PortfolioResearchValuation.from_snapshot(replace(source, positions=source.positions * 10001))
