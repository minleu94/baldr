"""個股圖表專用的 Decimal 指標序列；不供推薦或策略判斷使用。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class DisplayIndicatorSeries:
    rsi14: tuple[Decimal | None, ...]
    macd: tuple[Decimal | None, ...]
    signal: tuple[Decimal | None, ...]
    histogram: tuple[Decimal | None, ...]


def derive_display_indicators(
    closes: Sequence[Decimal | None],
) -> DisplayIndicatorSeries:
    """以圖表同源收盤價衍生 RSI(14) 與 MACD(12,26,9)。

    暖機不足、缺值或無效數字保留 ``None``；缺值會切斷序列，絕不補值。
    這是唯讀繪圖投影，不改寫來源資料、策略評分或推薦結果。
    """

    size = len(closes)
    rsi: list[Decimal | None] = [None] * size
    macd: list[Decimal | None] = [None] * size
    signal: list[Decimal | None] = [None] * size
    histogram: list[Decimal | None] = [None] * size
    with localcontext() as context:
        context.prec = 40
        for start, run in _valid_runs(closes):
            run_rsi = _wilder_rsi(run, 14)
            run_fast = _ema(run, 12)
            run_slow = _ema(run, 26)
            run_macd = tuple(
                fast - slow if fast is not None and slow is not None else None
                for fast, slow in zip(run_fast, run_slow)
            )
            run_signal = _ema(run_macd, 9)
            run_histogram = tuple(
                value - average if value is not None and average is not None else None
                for value, average in zip(run_macd, run_signal)
            )
            end = start + len(run)
            rsi[start:end] = run_rsi
            macd[start:end] = run_macd
            signal[start:end] = run_signal
            histogram[start:end] = run_histogram
    return DisplayIndicatorSeries(
        tuple(rsi), tuple(macd), tuple(signal), tuple(histogram)
    )


def _valid_runs(
    closes: Sequence[Decimal | None],
) -> tuple[tuple[int, tuple[Decimal, ...]], ...]:
    runs: list[tuple[int, tuple[Decimal, ...]]] = []
    start: int | None = None
    current: list[Decimal] = []
    for index, value in enumerate(closes):
        if not isinstance(value, Decimal) or not value.is_finite():
            if current and start is not None:
                runs.append((start, tuple(current)))
            start = None
            current = []
            continue
        if start is None:
            start = index
        current.append(value)
    if current and start is not None:
        runs.append((start, tuple(current)))
    return tuple(runs)


def _wilder_rsi(
    closes: Sequence[Decimal], period: int,
) -> tuple[Decimal | None, ...]:
    values: list[Decimal | None] = [None] * len(closes)
    if len(closes) <= period:
        return tuple(values)
    gains = [max(change, Decimal(0)) for change in _changes(closes)]
    losses = [max(-change, Decimal(0)) for change in _changes(closes)]
    average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
    average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
    values[period] = _rsi_value(average_gain, average_loss)
    for close_index in range(period + 1, len(closes)):
        change_index = close_index - 1
        average_gain = (
            average_gain * Decimal(period - 1) + gains[change_index]
        ) / Decimal(period)
        average_loss = (
            average_loss * Decimal(period - 1) + losses[change_index]
        ) / Decimal(period)
        values[close_index] = _rsi_value(average_gain, average_loss)
    return tuple(values)


def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_gain == 0 and average_loss == 0:
        return Decimal(50)
    if average_loss == 0:
        return Decimal(100)
    if average_gain == 0:
        return Decimal(0)
    relative_strength = average_gain / average_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)


def _ema(
    values: Sequence[Decimal | None], period: int,
) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    seed: list[Decimal] = []
    previous: Decimal | None = None
    multiplier = Decimal(2) / Decimal(period + 1)
    for index, value in enumerate(values):
        if value is None or not value.is_finite():
            seed = []
            previous = None
            continue
        if previous is None:
            seed.append(value)
            if len(seed) < period:
                continue
            previous = sum(seed, Decimal(0)) / Decimal(period)
            seed = []
        else:
            previous = (value - previous) * multiplier + previous
        result[index] = previous
    return tuple(result)


def _changes(closes: Sequence[Decimal]) -> tuple[Decimal, ...]:
    return tuple(current - previous for previous, current in zip(closes, closes[1:]))
