"""推薦 execution 保存與讀取所需的狹義資源組合入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation.save import RecommendationSaveService
from data_module.result_artifact_store import ResultArtifactStore


class _OutputPathConfig(Protocol):
    """能解析 caller-owned output path 的設定介面。"""

    def resolve_output_path(self, subfolder: str) -> Path: ...


@dataclass(frozen=True, slots=True)
class RecommendationComposition:
    """由單一 owner 持有的推薦 artifact store、writer 與 query。"""

    runs_dir: Path
    store: ResultArtifactStore
    persistence: RecommendationExecutionPersistence
    save_service: RecommendationSaveService
    queries: RecommendationExecutionQueries


def build_recommendation_composition(
    config: _OutputPathConfig,
) -> RecommendationComposition:
    """沿用 legacy recommendation runs 根目錄建立 canonical R012 資源。"""

    runs_dir = Path(config.resolve_output_path("recommendation/runs"))
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return RecommendationComposition(
        runs_dir=runs_dir,
        store=store,
        persistence=persistence,
        save_service=RecommendationSaveService(persistence),
        queries=RecommendationExecutionQueries(persistence),
    )


__all__ = ("RecommendationComposition", "build_recommendation_composition")
