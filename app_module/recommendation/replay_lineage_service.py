"""Replay parent/child lineage 的保存與實際 artifact 讀回驗證。"""

from __future__ import annotations

from datetime import date
from typing import Callable

from app_module.recommendation.contracts import (
    IndexStatus,
    RecommendationExecution,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.replay_lineage import (
    ReplayLineageChildV1,
    ReplayLineageReadEnvelope,
    ReplayLineageSidecarV1,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)


class ReplayLineagePersistenceError(RuntimeError):
    """Child artifact 未達可驗證的 indexed 保存狀態。"""


class ReplayLineageReadCancelledError(ReplayLineagePersistenceError):
    """逐筆 child 讀回收到明示取消；不發行部分驗證結果。"""


def persist_replay_lineage_children(
    result: RecommendationPortfolioBacktestResultDTO,
    persistence: RecommendationExecutionPersistence,
) -> ReplayLineageSidecarV1 | None:
    """先驗全部 child，再逐一 create-only 保存；缺 child 保留 v1 但不假造 lineage。"""

    if type(result) is not RecommendationPortfolioBacktestResultDTO:
        raise TypeError("result 必須是 RecommendationPortfolioBacktestResultDTO")
    if type(persistence) is not RecommendationExecutionPersistence:
        raise TypeError("persistence 必須是 RecommendationExecutionPersistence")
    parent_result_id = result.replay_parent_id
    if parent_result_id is None:
        return None

    prepared: list[tuple[ReplayLineageChildV1, RecommendationExecution]] = []
    for snapshot in result.snapshots:
        if snapshot.replay_parent_id != parent_result_id:
            raise ValueError("snapshot replay parent 與 portfolio parent 不一致")
        execution = snapshot.canonical_execution
        if execution is None:
            return None
        child = ReplayLineageChildV1.from_execution(
            execution,
            snapshot_date=date.fromisoformat(snapshot.as_of_date),
        )
        if child.replay_parent_ref.reference_id != parent_result_id:
            raise ValueError("child execution REPLAY_PARENT 與 portfolio parent 不一致")
        prepared.append((child, execution))

    # 同日/同 ID/parent 衝突在任何 artifact 寫入前就須拒絕。
    preliminary = ReplayLineageSidecarV1(
        parent_result_id=parent_result_id,
        children=tuple(child for child, _ in prepared),
    )
    for child, execution in prepared:
        receipt = persistence.save(execution)
        if receipt.index_status is not IndexStatus.INDEXED:
            raise ReplayLineagePersistenceError("child artifact 尚未完成索引")
        _, envelope = persistence.read_verified_envelope(child.result_id)
        child.verify_execution_artifact(envelope.raw_payload, receipt=receipt)
    return preliminary


def verify_replay_lineage_children(
    envelope: ReplayLineageReadEnvelope,
    persistence: RecommendationExecutionPersistence,
    *,
    check_cancel: Callable[[], bool] | None = None,
) -> tuple[RecommendationExecution, ...]:
    """對 Registry sidecar 列出的每個 child 讀取實際 bytes 並驗身份/hash。"""

    if type(envelope) is not ReplayLineageReadEnvelope:
        raise TypeError("envelope 必須是 ReplayLineageReadEnvelope")
    if type(persistence) is not RecommendationExecutionPersistence:
        raise TypeError("persistence 必須是 RecommendationExecutionPersistence")
    if check_cancel is not None and not callable(check_cancel):
        raise TypeError("check_cancel 必須可呼叫")
    if check_cancel is not None and check_cancel():
        raise ReplayLineageReadCancelledError("read_cancelled")
    verified: list[RecommendationExecution] = []
    for child in envelope.sidecar.children:
        if check_cancel is not None and check_cancel():
            raise ReplayLineageReadCancelledError("read_cancelled")
        _, execution_envelope = persistence.read_verified_envelope(child.result_id)
        verified.append(child.verify_execution_artifact(execution_envelope.raw_payload))
        if check_cancel is not None and check_cancel():
            raise ReplayLineageReadCancelledError("read_cancelled")
    return tuple(verified)


__all__ = (
    "ReplayLineagePersistenceError",
    "ReplayLineageReadCancelledError",
    "persist_replay_lineage_children",
    "verify_replay_lineage_children",
)
