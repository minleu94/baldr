"""版本化的臺銀證券電子下單成本估算。

本模組只處理研究／歷史回放用的估算，不代表實際券商對帳單，也不連線
券商或推定成交滑價。所有金額計算均留在 ``Decimal`` 邊界，股數使用
整數；需要顯示成 JSON 時才由 ``to_dict`` 轉成字串。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from enum import Enum
from typing import Any, Sequence, cast


BANKTAIWAN_ELECTRONIC_COST_POLICY_ID = "banktaiwan-electronic-order-v1"
BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION = "banktaiwan-electronic-order-2026-v1"
BANKTAIWAN_ELECTRONIC_POLICY_EFFECTIVE_FROM = date(2026, 1, 1)
BANKTAIWAN_ELECTRONIC_POLICY_EXPIRES_ON = date(2026, 12, 31)
BANKTAIWAN_ELECTRONIC_COMMISSION_RATE = Decimal("0.000498")
BANKTAIWAN_ORDINARY_STOCK_TAX_RATE = Decimal("0.003")
BANKTAIWAN_OTHER_APPROVED_SECURITY_TAX_RATE = Decimal("0.001")
BANKTAIWAN_FULL_LOT_SIZE = 1000
BANKTAIWAN_ODD_LOT_MAX_SHARES = 999
BANKTAIWAN_FULL_LOT_MINIMUM_COMMISSION = Decimal("20")
BANKTAIWAN_ODD_LOT_MINIMUM_COMMISSION = Decimal("1")

# Public aliases keep the policy constants discoverable without changing the
# longer names used by the application-facing API.
BANKTAIWAN_POLICY_ID = BANKTAIWAN_ELECTRONIC_COST_POLICY_ID
BANKTAIWAN_POLICY_VERSION = BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION


class BankTaiwanCostPolicyError(ValueError):
    """成本 policy 輸入或契約不合法。"""


class BankTaiwanPolicyUnavailableError(BankTaiwanCostPolicyError):
    """指定交易日沒有可用的版本。"""


class BankTaiwanPolicyExpiredError(BankTaiwanPolicyUnavailableError):
    """指定交易日已超出目前 policy 的有效期限。"""


class BankTaiwanAggregationError(BankTaiwanCostPolicyError):
    """同一 order id 的 fill identity 不一致，不能安全合併。"""


class BankTaiwanSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class BankTaiwanLotType(str, Enum):
    FULL_LOT = "full_lot"
    ODD_LOT = "odd_lot"


class BankTaiwanInstrumentType(str, Enum):
    ORDINARY_STOCK = "ordinary_stock"
    EQUITY_ETF = "equity_etf"
    # 相容英文呼叫端；值仍明確要求是 equity ETF，而非泛稱 ETF。
    ETF = "equity_etf"
    UNKNOWN = "unknown"


def _as_decimal(value: Decimal | int | str) -> Decimal:
    """將外部數值安全轉成 Decimal；拒絕二進位 float 進入核心。"""

    if isinstance(value, bool) or isinstance(value, float):
        raise BankTaiwanCostPolicyError("數值不可為 bool 或 float")
    try:
        converted = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BankTaiwanCostPolicyError(f"無法解析數值：{value!r}") from exc
    if not converted.is_finite():
        raise BankTaiwanCostPolicyError("數值必須是有限 Decimal")
    return converted


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_trade_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise BankTaiwanCostPolicyError(
                f"trade_date 必須是 ISO 日期：{value!r}"
            ) from exc
    raise BankTaiwanCostPolicyError("trade_date 必須是 date 或 ISO 日期字串")


def truncate_twd(value: Decimal | int | str) -> Decimal:
    """研究用整元截斷；呼叫者必須先確保輸入為非負金額。"""

    amount = _as_decimal(value)
    if amount < 0:
        raise BankTaiwanCostPolicyError("金額不可為負")
    return amount.quantize(Decimal("1"), rounding=ROUND_DOWN)


def _quantize_money(value: Decimal) -> Decimal:
    """以兩位小數保存成交金額，不使用 float。"""

    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_side(value: BankTaiwanSide | str) -> str:
    if isinstance(value, BankTaiwanSide):
        return value.value
    if not isinstance(value, str):
        raise BankTaiwanCostPolicyError("side 必須是 buy 或 sell")
    aliases = {
        "buy": BankTaiwanSide.BUY.value,
        "b": BankTaiwanSide.BUY.value,
        "買": BankTaiwanSide.BUY.value,
        "sell": BankTaiwanSide.SELL.value,
        "s": BankTaiwanSide.SELL.value,
        "賣": BankTaiwanSide.SELL.value,
    }
    normalized = aliases.get(_normalize_key(value))
    if normalized is None:
        raise BankTaiwanCostPolicyError(f"不支援的 side：{value!r}")
    return normalized


def _normalize_lot_type(value: BankTaiwanLotType | str) -> str:
    if isinstance(value, BankTaiwanLotType):
        return value.value
    if not isinstance(value, str):
        raise BankTaiwanCostPolicyError("lot_type 必須是 full_lot 或 odd_lot")
    aliases = {
        "full_lot": BankTaiwanLotType.FULL_LOT.value,
        "full": BankTaiwanLotType.FULL_LOT.value,
        "board_lot": BankTaiwanLotType.FULL_LOT.value,
        "regular": BankTaiwanLotType.FULL_LOT.value,
        "整股": BankTaiwanLotType.FULL_LOT.value,
        "odd_lot": BankTaiwanLotType.ODD_LOT.value,
        "odd": BankTaiwanLotType.ODD_LOT.value,
        "零股": BankTaiwanLotType.ODD_LOT.value,
    }
    normalized = aliases.get(_normalize_key(value))
    if normalized is None:
        raise BankTaiwanCostPolicyError(f"不支援的 lot_type：{value!r}")
    return normalized


def _normalize_instrument_type(value: BankTaiwanInstrumentType | str | None) -> str:
    if value is None:
        return BankTaiwanInstrumentType.UNKNOWN.value
    if isinstance(value, BankTaiwanInstrumentType):
        return value.value
    if not isinstance(value, str):
        raise BankTaiwanCostPolicyError("instrument_type 必須是支援的字串")
    aliases = {
        "ordinary_stock": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "ordinary_equity": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "common_stock": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "stock": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "equity": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "普通股": BankTaiwanInstrumentType.ORDINARY_STOCK.value,
        "equity_etf": BankTaiwanInstrumentType.EQUITY_ETF.value,
        "stock_etf": BankTaiwanInstrumentType.EQUITY_ETF.value,
        "non_bond_etf": BankTaiwanInstrumentType.EQUITY_ETF.value,
        "unknown": BankTaiwanInstrumentType.UNKNOWN.value,
        "": BankTaiwanInstrumentType.UNKNOWN.value,
        "未知": BankTaiwanInstrumentType.UNKNOWN.value,
    }
    if _normalize_key(value) in {
        "etf",
        "exchange_traded_fund",
        "指數股票型基金",
        "bond_etf",
        "債券etf",
        "other_approved_security",
        "other_security",
        "other",
        "其他有價證券",
    }:
        raise BankTaiwanCostPolicyError(
            "商品分類過於寬泛；請指定 ordinary_stock 或 equity_etf，"
            "債券 ETF／其他商品需另建明確稅務版本"
        )
    normalized = aliases.get(_normalize_key(value))
    if normalized is None:
        raise BankTaiwanCostPolicyError(f"不支援的 instrument_type：{value!r}")
    return normalized


def _validate_quantity_for_lot(quantity_shares: int, lot_type: str) -> None:
    if isinstance(quantity_shares, bool) or not isinstance(quantity_shares, int):
        raise BankTaiwanCostPolicyError("quantity_shares 必須是整數")
    if quantity_shares < 0:
        raise BankTaiwanCostPolicyError("quantity_shares 不可為負")
    if quantity_shares == 0:
        return
    if lot_type == BankTaiwanLotType.FULL_LOT.value:
        if quantity_shares % BANKTAIWAN_FULL_LOT_SIZE != 0:
            raise BankTaiwanCostPolicyError("整股數量必須是 1000 股的倍數")
        return
    if quantity_shares > BANKTAIWAN_ODD_LOT_MAX_SHARES:
        raise BankTaiwanCostPolicyError("零股數量必須介於 1 至 999 股")


@dataclass(frozen=True, slots=True)
class BankTaiwanOrder:
    """一筆訂單或一筆可聚合的成交 fill。"""

    order_id: str
    trade_date: date | str
    side: BankTaiwanSide | str
    price: Decimal | int | str
    quantity_shares: int
    lot_type: BankTaiwanLotType | str
    instrument_type: BankTaiwanInstrumentType | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise BankTaiwanCostPolicyError("order_id 不可為空")
        normalized_date = _normalize_trade_date(self.trade_date)
        normalized_side = _normalize_side(self.side)
        normalized_lot = _normalize_lot_type(self.lot_type)
        normalized_instrument = _normalize_instrument_type(self.instrument_type)
        normalized_price = _as_decimal(self.price)
        if normalized_price < 0:
            raise BankTaiwanCostPolicyError("price 不可為負")
        _validate_quantity_for_lot(self.quantity_shares, normalized_lot)
        if self.quantity_shares > 0 and normalized_price <= 0:
            raise BankTaiwanCostPolicyError("有成交股數時 price 必須大於 0")
        object.__setattr__(self, "trade_date", normalized_date)
        object.__setattr__(self, "side", normalized_side)
        object.__setattr__(self, "lot_type", normalized_lot)
        object.__setattr__(self, "instrument_type", normalized_instrument)
        object.__setattr__(self, "price", normalized_price)


@dataclass(frozen=True, slots=True)
class BankTaiwanCostEstimate:
    """可稽核的成本估算結果；核心 Decimal 不在此層轉 float。"""

    policy_id: str
    policy_version: str
    order_id: str
    trade_date: date
    side: str
    quantity_shares: int
    lot_type: str
    instrument_type: str
    gross_amount: Decimal
    commission: Decimal
    sell_tax: Decimal
    slippage: Decimal
    total_cost: Decimal
    commission_rate: Decimal
    sell_tax_rate: Decimal
    minimum_commission: Decimal
    status: str
    fill_count: int = 1
    price: Decimal | None = None
    warnings: tuple[str, ...] = ()

    @property
    def fee(self) -> Decimal:
        """與既有 consumer 使用的 fee 命名相容。"""

        return self.commission

    @property
    def tax(self) -> Decimal:
        return self.sell_tax

    def to_dict(self) -> dict[str, Any]:
        """在輸出邊界提供 JSON-safe 的字串金額。"""

        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "order_id": self.order_id,
            "trade_date": self.trade_date.isoformat(),
            "side": self.side,
            "quantity_shares": self.quantity_shares,
            "lot_type": self.lot_type,
            "instrument_type": self.instrument_type,
            "price": None if self.price is None else str(self.price),
            "gross_amount": str(self.gross_amount),
            "commission": str(self.commission),
            "fee": str(self.commission),
            "sell_tax": str(self.sell_tax),
            "tax": str(self.sell_tax),
            "slippage": str(self.slippage),
            "total_cost": str(self.total_cost),
            "commission_rate": str(self.commission_rate),
            "sell_tax_rate": str(self.sell_tax_rate),
            "minimum_commission": str(self.minimum_commission),
            "status": self.status,
            "fill_count": self.fill_count,
            "warnings": list(self.warnings),
        }


class BankTaiwanElectronicCostPolicy:
    """臺銀證券電子下單的單版本、交易日選擇、fail-closed 成本 policy。"""

    policy_id = BANKTAIWAN_ELECTRONIC_COST_POLICY_ID
    policy_version = BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
    effective_from = BANKTAIWAN_ELECTRONIC_POLICY_EFFECTIVE_FROM
    expires_on = BANKTAIWAN_ELECTRONIC_POLICY_EXPIRES_ON

    @staticmethod
    def normalize_lot_type(value: BankTaiwanLotType | str) -> str:
        return _normalize_lot_type(value)

    @staticmethod
    def normalize_instrument_type(
        value: BankTaiwanInstrumentType | str | None,
    ) -> str:
        return _normalize_instrument_type(value)

    @staticmethod
    def normalize_side(value: BankTaiwanSide | str) -> str:
        return _normalize_side(value)

    @staticmethod
    def lot_size_for(lot_type: BankTaiwanLotType | str) -> int:
        normalized = _normalize_lot_type(lot_type)
        if normalized == BankTaiwanLotType.FULL_LOT.value:
            return BANKTAIWAN_FULL_LOT_SIZE
        return 1

    @staticmethod
    def max_order_shares_for(lot_type: BankTaiwanLotType | str) -> int | None:
        """回傳單一委託的股數上限；整股沒有此 policy 上限。"""

        normalized = _normalize_lot_type(lot_type)
        if normalized == BankTaiwanLotType.ODD_LOT.value:
            return BANKTAIWAN_ODD_LOT_MAX_SHARES
        return None

    @staticmethod
    def _minimum_commission(lot_type: str) -> Decimal:
        if lot_type == BankTaiwanLotType.FULL_LOT.value:
            return BANKTAIWAN_FULL_LOT_MINIMUM_COMMISSION
        return BANKTAIWAN_ODD_LOT_MINIMUM_COMMISSION

    @staticmethod
    def _sell_tax_rate(instrument_type: str) -> Decimal:
        if instrument_type == BankTaiwanInstrumentType.ORDINARY_STOCK.value:
            return BANKTAIWAN_ORDINARY_STOCK_TAX_RATE
        if instrument_type == BankTaiwanInstrumentType.EQUITY_ETF.value:
            return BANKTAIWAN_OTHER_APPROVED_SECURITY_TAX_RATE
        return Decimal("0")

    def select_version(self, trade_date: date | str) -> str:
        """只以明確交易日選版本；到期或未生效時拒絕估算。"""

        normalized_date = _normalize_trade_date(trade_date)
        if normalized_date < self.effective_from:
            raise BankTaiwanPolicyUnavailableError(
                f"{self.policy_id} 尚未涵蓋交易日 {normalized_date.isoformat()}"
            )
        if normalized_date > self.expires_on:
            raise BankTaiwanPolicyExpiredError(
                f"{self.policy_id} 已於 {self.expires_on.isoformat()} 到期；"
                "請提供新的明確版本"
            )
        return self.policy_version

    def _validate_order(self, order: BankTaiwanOrder) -> BankTaiwanOrder:
        if not isinstance(order, BankTaiwanOrder):
            raise BankTaiwanCostPolicyError("estimate 需要 BankTaiwanOrder")
        self.select_version(order.trade_date)
        return order

    def _build_estimate(
        self,
        *,
        order_id: str,
        trade_date: date,
        side: str,
        quantity_shares: int,
        lot_type: str,
        instrument_type: str,
        gross_amount: Decimal,
        fill_count: int,
        price: Decimal | None,
    ) -> BankTaiwanCostEstimate:
        if instrument_type == BankTaiwanInstrumentType.UNKNOWN.value:
            raise BankTaiwanCostPolicyError(
                "未知商品不可估算臺銀證券完整成本；"
                "請提供明確 instrument_type"
            )
        minimum_commission = self._minimum_commission(lot_type)
        commission_rate = BANKTAIWAN_ELECTRONIC_COMMISSION_RATE
        sell_tax_rate = self._sell_tax_rate(instrument_type)
        status = "estimated" if quantity_shares > 0 else "no_trade"
        if quantity_shares == 0:
            commission = Decimal("0")
            sell_tax = Decimal("0")
            warnings: list[str] = ["no_fill_no_minimum_commission"]
        else:
            commission = max(
                truncate_twd(gross_amount * commission_rate),
                minimum_commission,
            )
            sell_tax = (
                truncate_twd(gross_amount * sell_tax_rate)
                if side == BankTaiwanSide.SELL.value and sell_tax_rate > 0
                else Decimal("0")
            )
            warnings = []
        warnings.extend(("broker_fill_not_observed", "slippage_not_modeled"))
        return BankTaiwanCostEstimate(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            order_id=order_id,
            trade_date=trade_date,
            side=side,
            quantity_shares=quantity_shares,
            lot_type=lot_type,
            instrument_type=instrument_type,
            price=price,
            gross_amount=_quantize_money(gross_amount),
            commission=commission,
            sell_tax=sell_tax,
            slippage=Decimal("0"),
            total_cost=commission + sell_tax,
            commission_rate=commission_rate,
            sell_tax_rate=sell_tax_rate,
            minimum_commission=minimum_commission,
            status=status,
            fill_count=fill_count,
            warnings=tuple(warnings),
        )

    def estimate(self, order: BankTaiwanOrder) -> BankTaiwanCostEstimate:
        """估算單筆訂單；零股與整股最低費用只在有成交時套用。"""

        validated = self._validate_order(order)
        trade_date = cast(date, validated.trade_date)
        side = cast(str, validated.side)
        lot_type = cast(str, validated.lot_type)
        instrument_type = cast(str, validated.instrument_type)
        price = cast(Decimal, validated.price)
        gross_amount = _quantize_money(
            price * validated.quantity_shares
        )
        return self._build_estimate(
            order_id=validated.order_id,
            trade_date=trade_date,
            side=side,
            quantity_shares=validated.quantity_shares,
            lot_type=lot_type,
            instrument_type=instrument_type,
            gross_amount=gross_amount,
            fill_count=1,
            price=price,
        )

    def estimate_many(
        self, orders: Sequence[BankTaiwanOrder]
    ) -> list[BankTaiwanCostEstimate]:
        """按委託 identity 聚合 fills，忽略成交價後只套一次最低費用。

        identity 為 ``order_id + trade_date + side + instrument_type + lot_type``。
        同一 order id 若出現其他 identity，直接拒絕，避免把一次委託靜默
        拆成多筆並重複收取最低費用。
        """

        if not orders:
            return []
        groups: dict[tuple[str, date, str, str, str], list[BankTaiwanOrder]] = {}
        identity_by_order_id: dict[str, tuple[date, str, str, str]] = {}
        for order in orders:
            validated = self._validate_order(order)
            trade_date = cast(date, validated.trade_date)
            side = cast(str, validated.side)
            instrument_type = cast(str, validated.instrument_type)
            lot_type = cast(str, validated.lot_type)
            identity = (
                trade_date,
                side,
                instrument_type,
                lot_type,
            )
            previous = identity_by_order_id.setdefault(validated.order_id, identity)
            if previous != identity:
                raise BankTaiwanAggregationError(
                    "同一 order_id 的 trade_date／side／instrument／lot 不一致，"
                    "不能安全聚合"
                )
            group_key = (
                validated.order_id,
                trade_date,
                side,
                instrument_type,
                lot_type,
            )
            groups.setdefault(group_key, []).append(validated)

        estimates: list[BankTaiwanCostEstimate] = []
        for (
            order_id,
            trade_date,
            side,
            instrument_type,
            lot_type,
        ), fills in groups.items():
            quantity_shares = sum(fill.quantity_shares for fill in fills)
            _validate_quantity_for_lot(quantity_shares, lot_type)
            fill_grosses = [
                _quantize_money(cast(Decimal, fill.price) * fill.quantity_shares)
                for fill in fills
            ]
            gross_amount = sum(fill_grosses, Decimal("0"))
            distinct_prices = {cast(Decimal, fill.price) for fill in fills}
            price = cast(Decimal, fills[0].price) if len(distinct_prices) == 1 else None
            estimate = self._build_estimate(
                order_id=order_id,
                trade_date=trade_date,
                side=side,
                quantity_shares=quantity_shares,
                lot_type=lot_type,
                instrument_type=instrument_type,
                gross_amount=gross_amount,
                fill_count=len(fills),
                price=price,
            )
            if side == BankTaiwanSide.SELL.value and quantity_shares > 0:
                # 證交稅以每次實際成交為邊界；聚合只合併最低手續費，
                # 不把不同 fill 的 fractional-TWD 稅額先合成一筆。
                sell_tax = sum(
                    (
                        truncate_twd(gross * estimate.sell_tax_rate)
                        for gross in fill_grosses
                    ),
                    Decimal("0"),
                )
                estimate = replace(
                    estimate,
                    sell_tax=sell_tax,
                    total_cost=estimate.commission + sell_tax,
                )
            if len(fills) > 1:
                estimate = replace(
                    estimate,
                    warnings=estimate.warnings
                    + ("multi_fill_order_aggregated",),
                )
            estimates.append(estimate)
        return estimates

    def metadata(
        self,
        *,
        lot_type: BankTaiwanLotType | str | None = None,
        instrument_type: BankTaiwanInstrumentType | str | None = None,
    ) -> dict[str, Any]:
        """回傳可寫入回測 manifest 的 policy metadata。"""

        normalized_lot = (
            None if lot_type is None else _normalize_lot_type(lot_type)
        )
        normalized_instrument = (
            None
            if instrument_type is None
            else _normalize_instrument_type(instrument_type)
        )
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "effective_from": self.effective_from.isoformat(),
            "expires_on": self.expires_on.isoformat(),
            "commission_rate": str(BANKTAIWAN_ELECTRONIC_COMMISSION_RATE),
            "commission_rate_percent": "0.0498%",
            "minimum_commission_twd": str(
                self._minimum_commission(normalized_lot)
                if normalized_lot is not None
                else BANKTAIWAN_FULL_LOT_MINIMUM_COMMISSION
            ),
            "minimum_commission_twd_by_lot": {
                "full_lot": str(BANKTAIWAN_FULL_LOT_MINIMUM_COMMISSION),
                "odd_lot": str(BANKTAIWAN_ODD_LOT_MINIMUM_COMMISSION),
            },
            "sell_tax_rate_by_instrument": {
                "ordinary_stock": str(BANKTAIWAN_ORDINARY_STOCK_TAX_RATE),
                "equity_etf": str(BANKTAIWAN_OTHER_APPROVED_SECURITY_TAX_RATE),
            },
            "unsupported_instrument_types": [
                "unknown",
                "generic_etf",
                "bond_etf",
                "other_approved_security",
            ],
            "lot_type": normalized_lot,
            "instrument_type": normalized_instrument,
            "full_lot_size_shares": BANKTAIWAN_FULL_LOT_SIZE,
            "odd_lot_max_order_shares": BANKTAIWAN_ODD_LOT_MAX_SHARES,
            "commission_rounding": "truncate_fractional_twd",
            "tax_rounding": "truncate_fractional_twd_per_fill_research_estimate",
            "order_aggregation": (
                "same order_id/date/side/instrument/lot; sum fill gross across prices; "
                "apply minimum once"
            ),
            "slippage": "not_modeled",
            "broker_fill_source": "not_observed",
            "cost_basis": "estimated_research_only",
        }


__all__ = [
    "BANKTAIWAN_ELECTRONIC_COMMISSION_RATE",
    "BANKTAIWAN_ELECTRONIC_COST_POLICY_ID",
    "BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION",
    "BANKTAIWAN_ELECTRONIC_POLICY_EFFECTIVE_FROM",
    "BANKTAIWAN_ELECTRONIC_POLICY_EXPIRES_ON",
    "BANKTAIWAN_FULL_LOT_MINIMUM_COMMISSION",
    "BANKTAIWAN_FULL_LOT_SIZE",
    "BANKTAIWAN_ODD_LOT_MINIMUM_COMMISSION",
    "BANKTAIWAN_ODD_LOT_MAX_SHARES",
    "BANKTAIWAN_ORDINARY_STOCK_TAX_RATE",
    "BANKTAIWAN_OTHER_APPROVED_SECURITY_TAX_RATE",
    "BANKTAIWAN_POLICY_ID",
    "BANKTAIWAN_POLICY_VERSION",
    "BankTaiwanAggregationError",
    "BankTaiwanCostEstimate",
    "BankTaiwanCostPolicyError",
    "BankTaiwanElectronicCostPolicy",
    "BankTaiwanInstrumentType",
    "BankTaiwanLotType",
    "BankTaiwanOrder",
    "BankTaiwanPolicyExpiredError",
    "BankTaiwanPolicyUnavailableError",
    "BankTaiwanSide",
    "truncate_twd",
]
