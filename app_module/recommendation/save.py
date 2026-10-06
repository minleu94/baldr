"""顯式推薦 execution 保存與 mutable metadata 命令。"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from app_module.recommendation.contracts import RecommendationExecution, SaveReceipt
from app_module.recommendation.persistence import RecommendationExecutionPersistence


class RecommendationSaveService:
    """唯一新 writer façade；輸入是已封存 execution，不讀 service latest state。"""

    def __init__(self, persistence: RecommendationExecutionPersistence) -> None:
        self._persistence = persistence

    def save_execution(
        self,
        execution: RecommendationExecution,
        *,
        label: str | None = None,
        notes: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> SaveReceipt:
        if now is None:
            return self._persistence.save(execution, label=label, notes=notes)
        return self._persistence.save(execution, label=label, notes=notes, now=now)

    def rename(self, result_id: str, label: str) -> None:
        """改名只寫 mutable metadata，payload bytes/hash 保持不變。"""

        self._persistence.rename(result_id, label)

    def update_notes(self, result_id: str, notes: str) -> None:
        """更新 notes 只寫 mutable metadata，payload bytes/hash 保持不變。"""

        self._persistence.update_notes(result_id, notes)


__all__ = ("RecommendationSaveService",)
