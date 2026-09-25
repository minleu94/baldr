"""RecommendationView 執行驗證與 sealed execution request。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable

from app_module.recommendation.contracts import (
    ExecutionStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
)
from app_module.recommendation.execute import execute_recommendation


ProgressCallback = Callable[[str, int], None]
CancellationCallback = Callable[[], bool]


def _config_snapshot(
    config: dict[str, Any],
) -> tuple[dict[str, Any], RecommendationConfigSnapshot]:
    """複製 caller 設定並保存其不可變 JSON／hash 快照。"""

    copied = deepcopy(config)
    # 這個來源標記只保存在 request snapshot；execute() 會從 runtime
    # config 移除，避免影響規則計算或策略選擇。
    copied["manual_qt_snapshot"] = True
    raw_json = json.dumps(
        copied,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    snapshot = RecommendationConfigSnapshot(
        raw_config_json=raw_json,
        raw_json_sha256="sha256:" + hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
    )
    return copied, snapshot


@dataclass(frozen=True)
class RecommendationExecutionRequest:
    """凍結一次 Qt caller 設定，回傳同次不可變 execution。"""

    config: dict[str, Any]
    max_stocks: int = 200
    top_n: int = 50
    config_snapshot: RecommendationConfigSnapshot = field(init=False)

    def __post_init__(self) -> None:
        copied, snapshot = _config_snapshot(self.config)
        object.__setattr__(self, "config", copied)
        object.__setattr__(self, "config_snapshot", snapshot)

    def validation_error(self) -> str | None:
        if not self.config.get("patterns", {}).get("selected", []):
            return "請至少選擇一個圖形模式"
        if not self.config.get("signals", {}).get("technical_indicators", []):
            return "請至少選擇一個技術指標"
        return None

    def execute(
        self,
        recommendation_service: Any,
        progress_callback: ProgressCallback | None = None,
        *,
        cancellation_callback: CancellationCallback | None = None,
        detailed_progress: bool = False,
    ) -> RecommendationExecution:
        """直接呼叫 execution use case，不投影成 legacy DTO list。"""

        def report_progress(stage: str, percentage: int) -> None:
            if progress_callback is None:
                return
            if stage == "recommendation_started":
                progress_callback("讀取股票數據...", percentage)
            elif stage == "recommendation_body_started":
                if detailed_progress:
                    progress_callback("建立分析範圍...", 25)
                progress_callback("執行推薦規則...", percentage)
            elif stage == "recommendation_body_finished":
                progress_callback("整理推薦結果...", percentage)
            elif stage == "recommendation_cancelled":
                progress_callback("分析已取消", percentage)
            elif stage == "recommendation_execution_finished":
                progress_callback("分析完成", percentage)

        if progress_callback is not None and not detailed_progress:
            def progress_without_details(stage: str, percentage: int) -> None:
                if stage in {"recommendation_started", "recommendation_cancelled", "recommendation_execution_finished"}:
                    report_progress(stage, percentage)

            use_case_progress: ProgressCallback | None = progress_without_details
        else:
            use_case_progress = report_progress if progress_callback is not None else None

        # 從 request snapshot 還原乾淨副本；caller 或其他 UI state 後續變更
        # 不會改寫已送出的推薦設定。
        runtime_config = json.loads(self.config_snapshot.raw_config_json)
        runtime_config.pop("manual_qt_snapshot", None)
        execution = execute_recommendation(
            recommendation_service,
            runtime_config,
            max_stocks=self.max_stocks,
            top_n=self.top_n,
            request_config_snapshot=self.config_snapshot,
            cancel=cancellation_callback,
            progress=use_case_progress,
        )
        if type(execution) is not RecommendationExecution:
            raise TypeError("推薦 execution use case 必須回傳 RecommendationExecution")
        if execution.status is not ExecutionStatus.COMPLETED:
            # cancelled / failed 是具名 terminal outcome，不以空 list 代替。
            return execution
        return execution
