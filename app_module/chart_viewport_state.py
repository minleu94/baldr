"""原生圖表的純日期槽範圍控制；不讀行情、不補值、不改投影資格。"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date
from typing import Sequence, TypeVar

T = TypeVar("T")


def _integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} 必須為整數")
    return value


def _date(value: str) -> str:
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("日期必須為 YYYY-MM-DD")
    return value


@dataclass(frozen=True)
class ChartViewportIdentity:
    """版本必須由 caller 明示；未知身份不可跨資料載入保留範圍。"""

    stock_code: str
    source_id: str
    version: str
    cutoff_date: str
    source_context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _date(self.cutoff_date)
        for value in (self.stock_code, self.source_id, self.version):
            if not isinstance(value, str):
                raise TypeError("身份欄位必須為字串")
        pairs = tuple(sorted(self.source_context))
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in pairs):
            raise TypeError("來源上下文必須為字串配對")
        if len({k for k, _ in pairs}) != len(pairs):
            raise ValueError("來源上下文 key 不可重複")
        object.__setattr__(self, "source_context", pairs)

    @property
    def complete(self) -> bool:
        def known(value: str) -> bool:
            return bool(value.strip()) and value.strip().lower() not in {
                "unknown", "n/a", "none", "未知",
            }

        return all(known(v) for v in (self.stock_code, self.source_id, self.version)) and all(
            known(k) and known(v) for k, v in self.source_context
        )


@dataclass(frozen=True)
class ChartViewportRange:
    """start 含、stop 不含；日期是原資料槽，不插入休市日。"""

    start: int = 0
    stop: int = 0
    total: int = 0
    first_date: str | None = None
    last_date: str | None = None

    @property
    def count(self) -> int:
        return self.stop - self.start

    @property
    def is_full(self) -> bool:
        return self.start == 0 and self.stop == self.total


class ChartViewportState:
    """只持有日期與身份，所有操作回傳 immutable range。

    同身份 reload 保留可見日期交集；無交集則全量重設。原本全量保持
    全量。空資料清除範圍；不快取其他股票的狀態。失敗 load 不改舊狀態。
    """

    def __init__(self) -> None:
        self._dates: tuple[str, ...] = ()
        self._identity: ChartViewportIdentity | None = None
        self._start = 0
        self._stop = 0

    @property
    def identity(self) -> ChartViewportIdentity | None:
        return self._identity

    @property
    def range(self) -> ChartViewportRange:
        return ChartViewportRange(
            self._start, self._stop, len(self._dates),
            self._dates[self._start] if self._stop > self._start else None,
            self._dates[self._stop - 1] if self._stop > self._start else None,
        )

    @property
    def visible_dates(self) -> tuple[str, ...]:
        return self._dates[self._start:self._stop]

    def load(
        self, dates: Sequence[str], identity: ChartViewportIdentity,
        *, preserve: bool = True,
    ) -> ChartViewportRange:
        """只接核對後 payload 日期；亂序、重複、cutoff 後資料拒絕。"""
        if not isinstance(identity, ChartViewportIdentity):
            raise TypeError("identity 必須為 ChartViewportIdentity")
        incoming = tuple(_date(value) for value in dates)
        if any(a >= b for a, b in zip(incoming, incoming[1:])):
            raise ValueError("日期必須嚴格遞增且不重複")
        if incoming and incoming[-1] > identity.cutoff_date:
            raise ValueError("viewport 不接受截止日後資料")
        previous = self.range
        compatible = preserve and identity.complete and self._identity == identity
        self._dates, self._identity = incoming, identity
        self.reset()
        if compatible and previous.count and not previous.is_full:
            assert previous.first_date is not None and previous.last_date is not None
            start = bisect_left(incoming, previous.first_date)
            stop = bisect_right(incoming, previous.last_date)
            if start < stop:
                self._start, self._stop = start, stop
        return self.range

    def reset(self) -> ChartViewportRange:
        self._start, self._stop = 0, len(self._dates)
        return self.range

    def set_range(self, start: int, stop: int) -> ChartViewportRange:
        """設定半開槽範圍；非空資料至少保留一槽，越界平移回合法範圍。"""
        _integer(start, "start")
        _integer(stop, "stop")
        if stop <= start:
            raise ValueError("stop 必須大於 start")
        return self._place(start, stop - start)

    def _place(self, start: int, count: int) -> ChartViewportRange:
        count = min(len(self._dates), max(1, count))
        self._start = max(0, min(start, len(self._dates) - count))
        self._stop = self._start + count
        return self.range

    def pan(self, slots: int) -> ChartViewportRange:
        """正數往較新資料移動，邊界保持原可見槽數。"""
        _integer(slots, "slots")
        return self._place(self._start + slots, self.range.count)

    def zoom(
        self, numerator: int, denominator: int = 1, *, anchor: int | None = None,
    ) -> ChartViewportRange:
        """新槽數 = 舊槽數 × numerator / denominator；小於 1 放大。

        anchor 是全量資料索引，預設可見中點；維持其相對位置，越界時
        clamp。比例只接受正整數，最少一槽；同槽縮小時至少縮一槽。
        """
        _integer(numerator, "numerator")
        _integer(denominator, "denominator")
        if numerator <= 0 or denominator <= 0:
            raise ValueError("縮放比例必須為正數")
        old = self.range
        if anchor is not None:
            _integer(anchor, "anchor")
            if not old.start <= anchor < old.stop:
                raise ValueError("anchor 必須在可見範圍內")
        if not old.count:
            return old
        target = max(1, (old.count * numerator + denominator // 2) // denominator)
        if numerator < denominator and old.count > 1:
            target = min(target, old.count - 1)
        elif numerator > denominator:
            target = max(target, old.count + 1)
        target = min(target, old.total)
        pivot = anchor if anchor is not None else old.start + (old.count - 1) // 2
        offset = 0 if old.count == 1 else (
            (pivot - old.start) * (target - 1) + (old.count - 1) // 2
        ) // (old.count - 1)
        return self._place(pivot - offset, target)

    def nearest_index(self, x: int, left: int, right: int) -> int | None:
        """renderer／hover 共用座標映射；缺價槽也回傳原始索引。"""
        for name, value in (("x", x), ("left", left), ("right", right)):
            _integer(value, name)
        if right <= left:
            raise ValueError("right 必須大於 left")
        if not self.range.count or x < left or x > right:
            return None
        span = right - left
        return self._start + (
            (x - left) * (self.range.count - 1) + span // 2
        ) // span

    def slice_points(self, points: Sequence[T]) -> tuple[T, ...]:
        """切核對後的原 DTO，保留 None；caller 須使用 load 的同份序列。"""
        if len(points) != len(self._dates):
            raise ValueError("資料槽數與已載入日期不一致")
        if tuple(getattr(point, "data_date", None) for point in points) != self._dates:
            raise ValueError("資料日期與已載入日期不一致")
        return tuple(points[self._start:self._stop])
