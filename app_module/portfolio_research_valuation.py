"""完整 Decimal 估值事實；顯示 bp 不替代實際現金或持倉股數。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Any

from app_module.paper_portfolio_snapshot_repository import PaperPortfolioPositionSnapshot, PaperPortfolioSnapshot
from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract, TOTAL_WEIGHT_BP, _payload_hash, _validate_decimal,
    _validate_int, _validate_non_empty,
)
from financial_module.units import quantize_money


_MAX_MONEY_CENTS = 10**17 - 1
_MAX_QUANTITY = 10**12
_MAX_POSITIONS = 10000


def _money_cents(name: str, value: Decimal) -> int:
    _validate_decimal(name, value, non_negative=True)
    parts = value.as_tuple()
    if (value.adjusted() > 15 or len(parts.digits) > 32
            or not isinstance(parts.exponent, int) or not -32 <= parts.exponent <= 15):
        raise ValueError(f"{name} exceeds exact monetary bound")
    # 檢查分單位而不依賴 caller 的 Decimal precision 或默默捨入輸入。
    numerator, denominator = value.as_integer_ratio()
    cents, remainder = divmod(numerator * 100, denominator)
    if remainder or cents > _MAX_MONEY_CENTS:
        raise ValueError(f"{name} must be bounded exact cents")
    return cents


def _money_text(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _price_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class PortfolioResearchValuedPosition:
    stock_code: str
    quantity: int
    mark_price: Decimal
    market_value: Decimal

    def __post_init__(self) -> None:
        canonical = _validate_non_empty("stock_code", self.stock_code)
        if canonical != self.stock_code or canonical.upper() == "CASH":
            raise ValueError("valued stock_code must be canonical and distinct from cash")
        _validate_int("quantity", self.quantity, minimum=1, maximum=_MAX_QUANTITY)
        _validate_decimal("mark_price", self.mark_price, positive=True)
        price_tuple = self.mark_price.as_tuple()
        if (len(price_tuple.digits) > 32 or not isinstance(price_tuple.exponent, int)
                or not -18 <= price_tuple.exponent <= 15):
            raise ValueError("mark_price exceeds exact price bound")
        cents = _money_cents("market_value", self.market_value)
        with localcontext(Context(prec=60)):
            expected = quantize_money(Decimal(self.quantity) * self.mark_price)
        if self.market_value != expected:
            raise ValueError("market_value differs from complete quantity and mark_price")
        object.__setattr__(self, "market_value", Decimal(_money_text(cents)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code, "quantity": self.quantity,
            "mark_price": _price_text(self.mark_price),
            "market_value": _money_text(_money_cents("market_value", self.market_value)),
        }


@dataclass(frozen=True)
class PortfolioResearchValuation:
    """金額守恆的同份估值；不包含來源或可得時鐘授權。"""

    cash_amount: Decimal
    total_value: Decimal
    positions: tuple[PortfolioResearchValuedPosition, ...]

    def __post_init__(self) -> None:
        cash_cents = _money_cents("cash_amount", self.cash_amount)
        nav_cents = _money_cents("total_value", self.total_value)
        if nav_cents <= 0:
            raise ValueError("total_value must be positive")
        if not isinstance(self.positions, tuple) or len(self.positions) > _MAX_POSITIONS or any(
            not isinstance(row, PortfolioResearchValuedPosition) for row in self.positions
        ):
            raise ValueError("positions must be a bounded tuple of complete valued positions")
        symbols = [row.stock_code for row in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate valued position")
        if cash_cents + sum(_money_cents("market_value", row.market_value) for row in self.positions) != nav_cents:
            raise ValueError("NAV must equal exact cash plus every position market value")
        object.__setattr__(self, "cash_amount", Decimal(_money_text(cash_cents)))
        object.__setattr__(self, "total_value", Decimal(_money_text(nav_cents)))
        object.__setattr__(self, "positions", tuple(sorted(self.positions, key=lambda row: row.stock_code)))

    @classmethod
    def from_snapshot(cls, snapshot: PaperPortfolioSnapshot) -> PortfolioResearchValuation:
        """核實體 snapshot 的全部估值；不推定其 receipt／clock／Health 有效。"""
        if not isinstance(snapshot, PaperPortfolioSnapshot):
            raise ValueError("complete PaperPortfolioSnapshot required")
        if not isinstance(snapshot.positions, tuple) or len(snapshot.positions) > _MAX_POSITIONS or any(
            not isinstance(row, PaperPortfolioPositionSnapshot) for row in snapshot.positions
        ):
            raise ValueError("snapshot positions must be a complete tuple")
        result = cls(
            cash_amount=snapshot.cash, total_value=snapshot.total_value,
            positions=tuple(PortfolioResearchValuedPosition(
                stock_code=row.stock_code, quantity=row.quantity,
                mark_price=row.mark_price, market_value=row.market_value,
            ) for row in snapshot.positions),
        )
        nav_cents = _money_cents("total_value", result.total_value)
        # 原 Paper snapshot 保存向下取整的股票 bp；只核該欄位，不由它還原金額。
        for source in snapshot.positions:
            expected = _money_cents("market_value", source.market_value) * TOTAL_WEIGHT_BP // nav_cents
            if source.weight_bp != expected:
                raise ValueError("snapshot weight differs from complete valuation")
        return result

    @property
    def display_weights(self) -> AllocationWeightContract:
        """用最大餘數分配顯示 bp；相同餘數按股票代碼及 CASH 排序。"""
        nav_cents = _money_cents("total_value", self.total_value)
        cents = {row.stock_code: _money_cents("market_value", row.market_value) for row in self.positions}
        cents["CASH"] = _money_cents("cash_amount", self.cash_amount)
        weights: dict[str, int] = {}
        remainders: dict[str, int] = {}
        for symbol, amount in cents.items():
            weights[symbol], remainders[symbol] = divmod(amount * TOTAL_WEIGHT_BP, nav_cents)
        remaining = TOTAL_WEIGHT_BP - sum(weights.values())
        for symbol in sorted(cents, key=lambda code: (-remainders[code], code))[:remaining]:
            weights[symbol] += 1
        cash_bp = weights.pop("CASH")
        # 0bp 但股數為正的持倉仍明示存在於契約，絕不過濾。
        return AllocationWeightContract(weights, cash_bp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "portfolio-research-valuation.v1",
            "cash_amount": _money_text(_money_cents("cash_amount", self.cash_amount)),
            "total_value": _money_text(_money_cents("total_value", self.total_value)),
            "positions": [row.to_dict() for row in self.positions],
            "display_method": "largest-remainder-bp.v1",
            "display_weights": self.display_weights.to_dict(),
        }

    @property
    def valuation_hash(self) -> str:
        return _payload_hash(self.to_dict())
