"""Replay execution 的版本化純 policy contract。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import gcd

from decision_module.recommendation.evaluation_constants import (
    MINIMUM_RECOMMENDATION_HISTORY_ROWS,
)


class ReplayRankingSemanticsV1(str, Enum):
    """固定 replay 的舊 Python float key 與反向穩定 list sort 語意。"""

    PYTHON_FLOAT_KEY_LIST_SORT_REVERSE_TRUE_STABLE = (
        "python_float_key_list_sort_reverse_true_stable"
    )


class ReplayScorerFailureSemanticsV1(str, Enum):
    """逐檔 scorer 例外在 replay v1 的外部行為。"""

    SILENT_SKIP_PER_STOCK = "silent_skip_per_stock"


class ReplayTopNSlicingSemanticsV1(str, Enum):
    """provider 與 snapshot wrapper 各自套用一次 Python slice。"""

    PROVIDER_THEN_SNAPSHOT_PYTHON_SLICE = (
        "provider_then_snapshot_python_slice"
    )


class ReplayScoreOrderingKindV1(str, Enum):
    """Replay 排序值的 tagged numeric 狀態。"""

    FINITE = "finite"
    NEGATIVE_INFINITY = "negative_infinity"
    UNORDERED_NAN = "unordered_nan"
    POSITIVE_INFINITY = "positive_infinity"


@dataclass(frozen=True, slots=True)
class ReplayScoreOrderingV1:
    """重現 replay v1 Python float key sort 的純排序 token。

    有限值以精確整數比表示；特殊值以 tag 表示。比較保留 Python 的
    partial-order 行為：NaN 與任何值互相比較皆不小於對方。此型別不是
    全序，也不做 float 轉換或算術；來源 dtype 的相容投影留在 app adapter。
    """

    kind: ReplayScoreOrderingKindV1
    numerator: int | None = None
    denominator: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplayScoreOrderingKindV1:
            raise TypeError("kind 必須是 ReplayScoreOrderingKindV1")
        if self.kind is ReplayScoreOrderingKindV1.FINITE:
            if type(self.numerator) is not int or type(self.denominator) is not int:
                raise TypeError("有限 ReplayScoreOrderingV1 必須提供整數分子與分母")
            if self.denominator <= 0:
                raise ValueError("有限 ReplayScoreOrderingV1 的分母必須大於零")
            divisor = gcd(abs(self.numerator), self.denominator)
            object.__setattr__(self, "numerator", self.numerator // divisor)
            object.__setattr__(self, "denominator", self.denominator // divisor)
        elif self.numerator is not None or self.denominator is not None:
            raise ValueError("非有限 ReplayScoreOrderingV1 不可帶分子或分母")

    @classmethod
    def finite(cls, numerator: int, denominator: int = 1) -> ReplayScoreOrderingV1:
        """建立有限精確比；只接受內建 int，不接受 bool 或 float。"""

        return cls(
            kind=ReplayScoreOrderingKindV1.FINITE,
            numerator=numerator,
            denominator=denominator,
        )

    @classmethod
    def negative_infinity(cls) -> ReplayScoreOrderingV1:
        return cls(ReplayScoreOrderingKindV1.NEGATIVE_INFINITY)

    @classmethod
    def nan(cls) -> ReplayScoreOrderingV1:
        return cls(ReplayScoreOrderingKindV1.UNORDERED_NAN)

    @classmethod
    def positive_infinity(cls) -> ReplayScoreOrderingV1:
        return cls(ReplayScoreOrderingKindV1.POSITIVE_INFINITY)

    def __lt__(self, other: ReplayScoreOrderingV1) -> bool:
        if not isinstance(other, ReplayScoreOrderingV1):
            raise TypeError("ReplayScoreOrderingV1 只能與相同型別比較")
        if (
            self.kind is ReplayScoreOrderingKindV1.UNORDERED_NAN
            or other.kind is ReplayScoreOrderingKindV1.UNORDERED_NAN
        ):
            return False

        self_rank = _replay_score_order_rank(self.kind)
        other_rank = _replay_score_order_rank(other.kind)
        if self_rank != other_rank:
            return self_rank < other_rank
        if self.kind is not ReplayScoreOrderingKindV1.FINITE:
            return False

        # __post_init__ 已驗證有限型別的比值欄位。
        assert self.numerator is not None and self.denominator is not None
        assert other.numerator is not None and other.denominator is not None
        return self.numerator * other.denominator < other.numerator * self.denominator


def _replay_score_order_rank(kind: ReplayScoreOrderingKindV1) -> int:
    if kind is ReplayScoreOrderingKindV1.NEGATIVE_INFINITY:
        return 0
    if kind is ReplayScoreOrderingKindV1.FINITE:
        return 1
    if kind is ReplayScoreOrderingKindV1.POSITIVE_INFINITY:
        return 2
    raise ValueError("NaN 沒有全序 rank，必須先套用 unordered 比較規則")


@dataclass(frozen=True, slots=True)
class ReplayExecutionPolicyV1:
    """固定 DataFrame replay v1 選股、歷史與排序語意的不可變描述。

    lookback 與 max stocks 是 app 已依舊規則完成 ``int()`` 轉換後的有效值；
    保留零與負數，因舊邊界分別採 ``lookback_days > 0`` 和 Python slice。
    ``top_n`` 也保留原始 signed int。此 contract 只描述策略，不執行篩選、
    排序或切片；尤其不替 NaN/Infinity 定義額外的全序。
    """

    top_n: int
    lookback_calendar_days: int = 80
    first_seen_max_stocks: int = 200
    schema_version: int = field(default=1, init=False)
    minimum_history_rows: int = field(
        default=MINIMUM_RECOMMENDATION_HISTORY_ROWS,
        init=False,
    )
    ranking_semantics: ReplayRankingSemanticsV1 = field(
        default=ReplayRankingSemanticsV1.PYTHON_FLOAT_KEY_LIST_SORT_REVERSE_TRUE_STABLE,
        init=False,
    )
    scorer_failure_semantics: ReplayScorerFailureSemanticsV1 = field(
        default=ReplayScorerFailureSemanticsV1.SILENT_SKIP_PER_STOCK,
        init=False,
    )
    top_n_slicing_semantics: ReplayTopNSlicingSemanticsV1 = field(
        default=ReplayTopNSlicingSemanticsV1.PROVIDER_THEN_SNAPSHOT_PYTHON_SLICE,
        init=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "top_n",
            "lookback_calendar_days",
            "first_seen_max_stocks",
        ):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} 必須是 int，不可使用 bool 或其他數值型別")
        if self.schema_version != 1:
            raise ValueError("ReplayExecutionPolicyV1 schema_version 必須是 1")
        if self.minimum_history_rows != MINIMUM_RECOMMENDATION_HISTORY_ROWS:
            raise ValueError("ReplayExecutionPolicyV1 的 minimum history 固定為 20")
        if type(self.ranking_semantics) is not ReplayRankingSemanticsV1:
            raise TypeError("ranking_semantics 必須是 ReplayRankingSemanticsV1")
        if type(self.scorer_failure_semantics) is not ReplayScorerFailureSemanticsV1:
            raise TypeError(
                "scorer_failure_semantics 必須是 ReplayScorerFailureSemanticsV1"
            )
        if type(self.top_n_slicing_semantics) is not ReplayTopNSlicingSemanticsV1:
            raise TypeError(
                "top_n_slicing_semantics 必須是 ReplayTopNSlicingSemanticsV1"
            )
