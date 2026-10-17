"""共用日價差方向契約，避免消費端把絕對值當成漲跌。"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from data_module.price_change_direction import (
    CHANGE_SIGN_COLUMNS as CHANGE_SIGN_COLUMNS,
    normalize_change_sign as normalize_change_sign,
)


def change_sign_columns(columns: Sequence[str]) -> tuple[str, ...]:
    """依既有優先序列出來源提供的方向欄。"""

    return tuple(name for name in CHANGE_SIGN_COLUMNS if name in columns)


def resolve_signed_change(
    value: object,
    sign_values: Sequence[object],
) -> tuple[Decimal | None, str]:
    """解析簽名價差；缺少可證方向的正值維持未知。"""

    if value is None or isinstance(value, bool):
        return None, ""
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None, ""
    if not amount.is_finite():
        return None, ""

    signs: list[str] = []
    has_unknown = False
    for raw_sign in sign_values:
        text = str(raw_sign or "").strip()
        if not text:
            continue
        sign = normalize_change_sign(text)
        if sign is None:
            has_unknown = True
        else:
            signs.append(sign)

    if has_unknown:
        return None, "unknown_change_direction"
    distinct_signs = set(signs)
    if len(distinct_signs) > 1:
        return None, "conflicting_change_direction"
    if amount < 0 and distinct_signs == {"+"}:
        return None, "conflicting_change_direction"
    if distinct_signs == {"-"}:
        return -abs(amount), ""
    if distinct_signs == {"+"}:
        return abs(amount), ""
    if amount < 0:
        return amount, ""
    if amount == 0:
        return amount, ""
    return None, "missing_change_direction"
