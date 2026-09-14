"""臺銀證券電子下單成本 policy 的精度、版本與聚合契約。"""

from datetime import date
from decimal import Decimal
import json

import pytest

from financial_module.banktaiwan_cost_policy import (
    BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION,
    BankTaiwanAggregationError,
    BankTaiwanCostPolicyError,
    BankTaiwanElectronicCostPolicy,
    BankTaiwanPolicyExpiredError,
    BankTaiwanPolicyUnavailableError,
    BankTaiwanOrder,
)


def _order(
    *,
    order_id: str = "order-1",
    side: str = "buy",
    price: str = "100",
    quantity: int = 1000,
    lot_type: str = "full_lot",
    instrument_type: str = "ordinary_stock",
    trade_date: str = "2026-09-14",
) -> BankTaiwanOrder:
    return BankTaiwanOrder(
        order_id=order_id,
        trade_date=trade_date,
        side=side,
        price=price,
        quantity_shares=quantity,
        lot_type=lot_type,
        instrument_type=instrument_type,
    )


def test_full_lot_commission_uses_banktaiwan_rate_and_twenty_minimum():
    policy = BankTaiwanElectronicCostPolicy()

    estimate = policy.estimate(_order(price="100", quantity=1000))

    assert estimate.policy_version == BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
    assert estimate.gross_amount == Decimal("100000.00")
    assert estimate.commission == Decimal("49")
    assert estimate.sell_tax == Decimal("0")
    assert estimate.total_cost == Decimal("49")
    assert estimate.minimum_commission == Decimal("20")

    small = policy.estimate(_order(price="10", quantity=1000))
    assert small.gross_amount == Decimal("10000.00")
    assert small.commission == Decimal("20")


def test_odd_lot_minimum_and_no_trade_do_not_charge_minimum():
    policy = BankTaiwanElectronicCostPolicy()

    odd_lot = policy.estimate(
        _order(price="0.01", quantity=1, lot_type="odd_lot")
    )
    no_trade = policy.estimate(
        _order(price="0", quantity=0, lot_type="full_lot")
    )

    assert odd_lot.commission == Decimal("1")
    assert odd_lot.status == "estimated"
    assert no_trade.commission == Decimal("0")
    assert no_trade.sell_tax == Decimal("0")
    assert no_trade.total_cost == Decimal("0")
    assert no_trade.status == "no_trade"


def test_sell_tax_is_separate_for_ordinary_stock_and_explicit_equity_etf():
    policy = BankTaiwanElectronicCostPolicy()

    stock = policy.estimate(_order(side="sell", quantity=1000, price="100"))
    equity_etf = policy.estimate(
        _order(
            side="sell",
            quantity=1000,
            price="100",
            instrument_type="equity_etf",
        )
    )

    assert stock.sell_tax == Decimal("300")
    assert stock.total_cost == Decimal("349")
    assert equity_etf.sell_tax == Decimal("100")
    assert equity_etf.total_cost == Decimal("149")


def test_generic_etf_and_other_security_are_not_silently_mapped_to_one_per_mille():
    metadata = BankTaiwanElectronicCostPolicy().metadata()
    assert "unknown" not in metadata["sell_tax_rate_by_instrument"]
    assert "unknown" in metadata["unsupported_instrument_types"]
    with pytest.raises(BankTaiwanCostPolicyError, match="過於寬泛"):
        _order(instrument_type="ETF")
    with pytest.raises(BankTaiwanCostPolicyError, match="過於寬泛"):
        _order(instrument_type="other_approved_security")
    with pytest.raises(BankTaiwanCostPolicyError, match="未知商品"):
        BankTaiwanElectronicCostPolicy().estimate(_order(instrument_type="unknown"))


def test_float_is_rejected_at_policy_core_boundary():
    with pytest.raises(BankTaiwanCostPolicyError, match="float"):
        _order(price=100.0)  # type: ignore[arg-type]


def test_policy_is_trade_date_versioned_and_fails_closed_after_expiry():
    policy = BankTaiwanElectronicCostPolicy()

    assert policy.select_version(date(2026, 1, 1)) == BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
    with pytest.raises(BankTaiwanPolicyUnavailableError):
        policy.estimate(_order(trade_date="2025-12-31"))
    with pytest.raises(BankTaiwanPolicyExpiredError):
        policy.estimate(_order(trade_date="2027-01-01"))


def test_same_order_different_prices_aggregates_gross_before_one_minimum():
    policy = BankTaiwanElectronicCostPolicy()
    fills = [
        _order(order_id="same", price="0.01", quantity=1000),
        _order(order_id="same", price="0.02", quantity=1000),
    ]

    estimate = policy.estimate_many(fills)[0]

    assert estimate.fill_count == 2
    assert estimate.price is None
    assert estimate.gross_amount == Decimal("30.00")
    assert estimate.commission == Decimal("20")
    assert "multi_fill_order_aggregated" in estimate.warnings


def test_multi_fill_sell_tax_is_truncated_per_fill_not_as_an_unknown_order_tax():
    policy = BankTaiwanElectronicCostPolicy()
    estimate = policy.estimate_many(
        [
            _order(order_id="sell-same", side="sell", price="0.2", quantity=1000),
            _order(order_id="sell-same", side="sell", price="0.2", quantity=1000),
        ]
    )[0]

    # Each fill is TWD 200, so 3‰ is TWD 0.6 and truncates to zero.
    assert estimate.gross_amount == Decimal("400.00")
    assert estimate.sell_tax == Decimal("0")
    assert estimate.commission == Decimal("20")


def test_different_orders_each_receive_their_own_minimum_and_identity_mismatch_fails():
    policy = BankTaiwanElectronicCostPolicy()
    separate = policy.estimate_many(
        [
            _order(order_id="a", price="0.01", quantity=1000),
            _order(order_id="b", price="0.01", quantity=1000),
        ]
    )
    assert [item.commission for item in separate] == [Decimal("20"), Decimal("20")]

    with pytest.raises(BankTaiwanAggregationError):
        policy.estimate_many(
            [
                _order(order_id="same", side="buy"),
                _order(order_id="same", side="sell"),
            ]
        )


def test_lot_boundaries_are_integer_and_explicit():
    with pytest.raises(BankTaiwanCostPolicyError):
        _order(quantity=999, lot_type="full_lot")
    with pytest.raises(BankTaiwanCostPolicyError):
        _order(quantity=1000, lot_type="odd_lot")
    assert _order(quantity=999, lot_type="odd_lot").quantity_shares == 999


def test_cli_entry_supports_repeatable_different_price_fills(capsys):
    from scripts.estimate_banktaiwan_cost import main

    assert main(
        [
            "--order-id",
            "cli-order",
            "--trade-date",
            "2026-09-14",
            "--side",
            "buy",
            "--lot-type",
            "full_lot",
            "--instrument-type",
            "ordinary_stock",
            "--fill",
            "0.01:1000",
            "--fill",
            "0.02:1000",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fill_count"] == 2
    assert payload["gross_amount"] == "30.00"
    assert payload["commission"] == "20"
