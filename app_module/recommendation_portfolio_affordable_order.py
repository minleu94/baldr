"""有限步數搜尋 next-open 委託可負擔股數。"""

from __future__ import annotations

from collections.abc import Callable


class AffordableOrderCancelledError(RuntimeError):
    """搜尋期間收到取消要求。"""


def max_affordable_lot_shares(
    *,
    requested_shares: int,
    lot_size: int,
    is_affordable: Callable[[int], bool],
    check_cancel: Callable[[], bool] | None = None,
) -> int:
    """回傳預定股數範圍內最大的可負擔整手股數。

    呼叫端須在目前適用的成本模型下提供單調 predicate；本 helper 只搜尋
    整數 lot 數，不驗證任意 predicate 的單調性，也不改寫或近似成本計算。
    每次成本判定前都會檢查取消旗標。零手上限直接回傳零且不呼叫成本函式。
    """

    if type(requested_shares) is not int:
        raise TypeError("requested_shares 必須是 int")
    if type(lot_size) is not int:
        raise TypeError("lot_size 必須是 int")
    if requested_shares < 0:
        raise ValueError("requested_shares 不可小於零")
    if lot_size <= 0:
        raise ValueError("lot_size 必須大於零")
    if not callable(is_affordable):
        raise TypeError("is_affordable 必須可呼叫")
    if check_cancel is not None and not callable(check_cancel):
        raise TypeError("check_cancel 必須是可呼叫物件或 None")

    max_lots = requested_shares // lot_size
    if max_lots == 0:
        return 0

    def require_not_cancelled() -> None:
        if check_cancel is None:
            return
        cancelled = check_cancel()
        if type(cancelled) is not bool:
            raise TypeError("check_cancel 必須回傳 bool")
        if cancelled:
            raise AffordableOrderCancelledError("可負擔股數搜尋已取消")

    def evaluate(lot_count: int) -> bool:
        require_not_cancelled()
        affordable = is_affordable(lot_count * lot_size)
        if type(affordable) is not bool:
            raise TypeError("is_affordable 必須回傳 bool")
        return affordable

    if evaluate(max_lots):
        return max_lots * lot_size
    # 保留原最大股數／相鄰一手的成本判定順序，最低費用只差一手時
    # 不新增中間詢價；差距更大才進入有界搜尋。
    if max_lots > 1 and evaluate(max_lots - 1):
        return (max_lots - 1) * lot_size

    # 零手是不需詢價即可成立的下界；high 則是已判定不可負擔的上界。
    low_lots = 0
    high_lots = max_lots - 1 if max_lots > 1 else max_lots
    while high_lots - low_lots > 1:
        middle_lots = (low_lots + high_lots) // 2
        if evaluate(middle_lots):
            low_lots = middle_lots
        else:
            high_lots = middle_lots

    return low_lots * lot_size


__all__ = ["AffordableOrderCancelledError", "max_affordable_lot_shares"]
