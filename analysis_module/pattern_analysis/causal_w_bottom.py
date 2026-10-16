"""逐日可知的W底收盤價研究核心；不使用全段極值、浮點數或未來填補。"""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, DecimalException, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
from typing import Any


def price_decimal(value: Any) -> Decimal | None:
    """原行情轉換邊界；缺值未知，非正／無限／超精度價格拒絕。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("價格不可為布林值")
    try:
        number = Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        return None
    if number.is_nan():
        return None
    if not number.is_finite() or number <= 0:
        raise ValueError("W底研究OHLC須為有限正價格")
    digits = number.as_tuple()
    if (not isinstance(digits.exponent, int) or digits.exponent < -12
            or len(digits.digits) + max(digits.exponent, 0) > 28):
        raise ValueError("W底研究價格超出28位／小數12位精度契約")
    return number


@dataclass(frozen=True)
class WBottomEvidence:
    first_trough_at: date
    second_trough_at: date
    neckline_at: date
    confirmed_at: date
    first_trough: Decimal
    second_trough: Decimal
    neckline: Decimal
    floor: Decimal


@dataclass(frozen=True)
class WBottomObservation:
    when: date
    close: Decimal | None
    ready: bool
    signal: int
    reason: str
    state: str
    evidence: WBottomEvidence | None = None


@dataclass(frozen=True)
class _Point:
    position: int
    when: date
    close: Decimal


@dataclass(frozen=True)
class _Trough:
    point: _Point
    prior_decline: bool


def _geometry(first: _Trough, second: _Trough, history: list[_Point], when: date) -> WBottomEvidence | None:
    left, right = first.point, second.point
    separation = right.position - left.position
    if not first.prior_decline or not 3 <= separation <= 20:
        return None
    between = [point for point in history if left.position < point.position < right.position]
    if len(between) != separation - 1:
        return None
    neck = max(between, key=lambda point: point.close)
    if (abs(left.close - right.close) * 10000 > left.close * 500
            or neck.close * 10000 <= left.close * 10100
            or neck.close * 10000 <= right.close * 10100):
        return None
    return WBottomEvidence(left.when, right.when, neck.when, when, left.close, right.close,
                           neck.close, min(left.close, right.close))


def observe_w_bottom(prices: Sequence[tuple[date, Decimal | None]], *,
                     max_wait_sessions: int = 20, start: date | None = None) -> list[WBottomObservation]:
    """一次線性掃描，只保留27列；候選與訊號episode都不是已成交部位。"""
    if type(max_wait_sessions) is not int or max_wait_sessions not in (5, 10, 20):
        raise ValueError("W底等待參數不符契約")
    if start is not None and type(start) is not date:
        raise ValueError("W底測試開始日須為date")
    history: list[_Point] = []
    previous_trough: _Trough | None = None
    candidate: WBottomEvidence | None = None
    confirmed_position: int | None = None
    episode: WBottomEvidence | None = None
    observations: list[WBottomObservation] = []
    previous_date: date | None = None
    fixed_context = Context(prec=60, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                            capitals=1, clamp=0, traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(fixed_context):
        for position, (when, close) in enumerate(prices):
            if type(when) is not date or previous_date is not None and when <= previous_date:
                raise ValueError("W底日期須唯一且遞增")
            previous_date = when
            if close is not None:
                if not isinstance(close, Decimal):
                    raise ValueError("W底核心只接受Decimal價格")
                close = price_decimal(close)
            if start is not None and when < start:
                observations.append(WBottomObservation(when, close, False, 0, "context_only_no_order", "warming"))
                continue
            if close is None:
                history = []; previous_trough = None; candidate = None; confirmed_position = None
                observations.append(WBottomObservation(when, None, False, 0, "missing_ohlc_reset_geometry",
                                    "intent_episode" if episode else "warming", episode))
                continue
            point = _Point(position, when, close)
            if episode is not None:
                if close < episode.neckline:
                    observations.append(WBottomObservation(when, close, True, -1, "below_frozen_neckline_exit_intent", "exit_intent", episode))
                    episode = None; history = [point]; previous_trough = None
                else:
                    observations.append(WBottomObservation(when, close, True, 0, "intent_episode_hold", "intent_episode", episode))
                continue
            if candidate is not None and confirmed_position is not None and (
                    close < candidate.floor or position - confirmed_position > max_wait_sessions):
                reason = "candidate_below_floor" if close < candidate.floor else "candidate_expired"
                observations.append(WBottomObservation(when, close, True, 0, reason, "invalidated", candidate))
                candidate = None; confirmed_position = None; previous_trough = None; history = [point]
                continue
            history.append(point)
            history = history[-27:]
            ready = len(history) >= 7
            if len(history) >= 3 and history[-2].close < min(history[-3].close, point.close):
                prior = history[-7:-2] if len(history) >= 7 else []
                decline = (len(prior) == 5
                           and sum((item.close for item in prior[:3]), Decimal(0)) * 2
                           > sum((item.close for item in prior[3:]), Decimal(0)) * 3)
                current_trough = _Trough(history[-2], decline)
                if candidate is None and previous_trough is not None:
                    candidate = _geometry(previous_trough, current_trough, history, when)
                    if candidate is not None:
                        confirmed_position = position
                previous_trough = current_trough
            if candidate is not None and len(history) >= 2 and history[-2].close <= candidate.neckline < close:
                episode = candidate
                observations.append(WBottomObservation(when, close, True, 1, "neckline_cross_entry_intent", "entry_intent", candidate))
                candidate = None; confirmed_position = None; previous_trough = None; history = []
            else:
                reason = "candidate_waiting_neckline_cross" if candidate else "no_confirmed_pattern" if ready else "warming_predecline"
                observations.append(WBottomObservation(when, close, ready, 0, reason, "candidate" if candidate else "observing" if ready else "warming", candidate))
    return observations
