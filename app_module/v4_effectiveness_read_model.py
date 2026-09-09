"""V4 有效性證據的唯讀 read model。

V3 的事件分組介面仍保留給既有 UI 與相容 caller。V4 read model 使用較
嚴格的 cohort 契約，將決策日、持有期間、策略／股票池、成本模型與
benchmark 分開，避免不同實驗或不同成熟度被混在同一個統計量內。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app_module.v4_effectiveness_evaluator import (
    V4EffectivenessReport,
    evaluate_v4_effectiveness,
)


class V4EffectivenessReadModel:
    """從已保存證據建立 V4 唯讀報告，不產生交易或 lifecycle 動作。"""

    def __init__(
        self,
        *,
        k: int = 10,
        minimum_decision_days: int = 3,
        minimum_mature_outcomes: int = 20,
    ) -> None:
        if k <= 0 or minimum_decision_days <= 0 or minimum_mature_outcomes <= 0:
            raise ValueError("V4 effectiveness thresholds must be positive")
        self._k = int(k)
        self._minimum_decision_days = int(minimum_decision_days)
        self._minimum_mature_outcomes = int(minimum_mature_outcomes)

    def build_report(
        self,
        *,
        rows: Iterable[Mapping[str, Any]],
    ) -> V4EffectivenessReport:
        """建立 strict cohort report；輸入可來自 SQLite read model 或 JSONL。"""

        return evaluate_v4_effectiveness(
            rows,
            k=self._k,
            minimum_decision_days=self._minimum_decision_days,
            minimum_mature_outcomes=self._minimum_mature_outcomes,
        )


__all__ = ["V4EffectivenessReadModel"]
