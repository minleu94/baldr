"""推薦 calibration learning 的隔離輸出根目錄契約。

推薦 learning 是 shadow artifact producer／consumer；它不能沿用正式資料根目錄
或一般產品的 ``OUTPUT_ROOT``。本模組是 scheduler、runner、consumer 與 Workbench
共同使用的唯一 root resolver，保留通用 shadow artifact loader 的 fail-closed 規則。
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV = "RECOMMENDATION_LEARNING_OUTPUT_ROOT"
DEFAULT_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")
DEFAULT_RECOMMENDATION_LEARNING_OUTPUT_DIRNAME = "FA_Data_Shadow"


class RecommendationLearningPathError(ValueError):
    """推薦 learning root 不符合 shadow custody 時拋出的明確錯誤。"""


@dataclass(frozen=True)
class RecommendationLearningPaths:
    """Resolved paths shared by the learning producer and read-only consumers."""

    data_root: Path
    output_root: Path

    @property
    def learning_root(self) -> Path:
        return self.output_root / "recommendation_learning"

    @property
    def latest_status_path(self) -> Path:
        return self.learning_root / "latest_status.json"

    @property
    def active_pointer_path(self) -> Path:
        return self.learning_root / "recommendation-calibration-active-pointer.json"


def resolve_recommendation_learning_paths(
    *,
    data_root: str | Path | None = None,
    explicit_output_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> RecommendationLearningPaths:
    """Resolve and validate the recommendation-learning shadow root.

    ``explicit_output_root`` is the CLI／caller override. If it is omitted,
    only ``RECOMMENDATION_LEARNING_OUTPUT_ROOT`` is considered; the generic
    product ``OUTPUT_ROOT`` is deliberately not inherited. With no override,
    formal ``D:\\Min\\Python\\Project\\FA_Data`` resolves to the sibling
    ``D:\\Min\\Python\\Project\\FA_Data_Shadow`` root.
    """

    env = os.environ if environ is None else environ
    raw_data_root = data_root if data_root is not None else env.get("DATA_ROOT")
    formal_root = Path(raw_data_root or DEFAULT_DATA_ROOT).resolve()

    configured_root = (
        explicit_output_root
        if explicit_output_root is not None
        else env.get(RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV)
    )
    if configured_root is None or not str(configured_root).strip():
        shadow_root = (formal_root.parent / DEFAULT_RECOMMENDATION_LEARNING_OUTPUT_DIRNAME).resolve()
        source = "default sibling shadow root"
    else:
        raw_shadow_root = Path(str(configured_root).strip())
        if not raw_shadow_root.is_absolute():
            raise RecommendationLearningPathError(
                f"{RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV} must be an absolute path outside "
                f"DATA_ROOT; got {configured_root!r}"
            )
        shadow_root = raw_shadow_root.resolve()
        source = "explicit recommendation-learning output root"

    if shadow_root == formal_root or formal_root in shadow_root.parents:
        raise RecommendationLearningPathError(
            "recommendation learning output root is unsafe: it must be outside DATA_ROOT; "
            f"DATA_ROOT={formal_root}; resolved_root={shadow_root}; source={source}. "
            f"Set {RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV} to an absolute sibling or other "
            "isolated shadow directory."
        )
    return RecommendationLearningPaths(data_root=formal_root, output_root=shadow_root)


def resolve_recommendation_learning_output_root(
    *,
    data_root: str | Path | None = None,
    explicit_output_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Convenience resolver for callers that only need the shared output root."""

    return resolve_recommendation_learning_paths(
        data_root=data_root,
        explicit_output_root=explicit_output_root,
        environ=environ,
    ).output_root
