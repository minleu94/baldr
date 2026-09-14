"""估算臺銀證券電子下單成本的命令列入口。

此入口只產生研究用估算，不連線券商、不取得實際成交回報，也不模擬滑價。
``--fill`` 可重複指定同一 order 的不同價格成交，驗證最低手續費只套一次。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from financial_module.banktaiwan_cost_policy import (
    BankTaiwanElectronicCostPolicy,
    BankTaiwanOrder,
)


def _parse_fill(value: str) -> tuple[Decimal, int]:
    try:
        price_text, quantity_text = value.split(":", 1)
        price = Decimal(price_text.strip())
        quantity = int(quantity_text.strip())
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "fill 格式必須是 PRICE:QUANTITY_SHARES"
        ) from exc
    if not price.is_finite() or price < 0 or quantity < 0:
        raise argparse.ArgumentTypeError("fill 的價格與股數必須是非負有限值")
    return price, quantity


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estimate BankTaiwan Securities electronic order cost")
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--trade-date", required=True, help="ISO date, e.g. 2026-09-14")
    parser.add_argument("--side", required=True, choices=("buy", "sell"))
    parser.add_argument("--lot-type", required=True, choices=("full_lot", "odd_lot"))
    parser.add_argument(
        "--instrument-type",
        required=True,
        choices=("ordinary_stock", "equity_etf"),
    )
    parser.add_argument("--price", help="single-fill price")
    parser.add_argument("--quantity-shares", type=int, help="single-fill share count")
    parser.add_argument(
        "--fill",
        action="append",
        type=_parse_fill,
        help="repeatable fill in PRICE:QUANTITY_SHARES form",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _orders_from_args(args: argparse.Namespace) -> list[BankTaiwanOrder]:
    if args.fill:
        if args.price is not None or args.quantity_shares is not None:
            raise ValueError("--fill 不可與 --price/--quantity-shares 混用")
        fills = args.fill
    else:
        if args.price is None or args.quantity_shares is None:
            raise ValueError("單一成交需要同時指定 --price 與 --quantity-shares")
        fills = [(Decimal(args.price), args.quantity_shares)]
    return [
        BankTaiwanOrder(
            order_id=args.order_id,
            trade_date=date.fromisoformat(args.trade_date),
            side=args.side,
            price=price,
            quantity_shares=quantity,
            lot_type=args.lot_type,
            instrument_type=args.instrument_type,
        )
        for price, quantity in fills
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        orders = _orders_from_args(args)
        policy = BankTaiwanElectronicCostPolicy()
        estimates = policy.estimate_many(orders) if args.fill else [policy.estimate(orders[0])]
    except (ValueError, InvalidOperation) as exc:
        parser.error(str(exc))
    if args.format == "json":
        payload = estimates[0].to_dict() if len(estimates) == 1 else [item.to_dict() for item in estimates]
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        for estimate in estimates:
            print(
                f"{estimate.policy_version} {estimate.side} "
                f"shares={estimate.quantity_shares} gross={estimate.gross_amount} "
                f"commission={estimate.commission} tax={estimate.sell_tax} "
                f"total={estimate.total_cost}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
