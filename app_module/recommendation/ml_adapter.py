"""推薦應用層的明示 ML 準備與投影介面。

本模組只定義結構式 Protocol，不讀取 provider 或檔案，
不建立特徵、不載入模型，也不執行推論。
"""

from __future__ import annotations

from typing import Mapping, Protocol, TypeVar

from app_module.recommendation.contracts import RecommendationExecution
from ml_module.prepared_input_contract import (
    CandidateIdentity,
    PreparedMLInput,
    SnapshotReference,
)
from app_module.recommendation.prepared_runtime_input import PreparedMLRuntimeInputV1


_ProjectionT = TypeVar("_ProjectionT", covariant=True)


class RecommendationMLAdapter(Protocol):
    """應用層 ML 準備邊界。

    呼叫者必須明確傳入 mode，因為 RecommendationExecution.Context 尚未定義執行模式。
    實作必須回傳實際使用的不可變 references，
    此 Protocol 不提供即時來源 fallback。
    僅有 available_date 時保留日期精度，不得補成午夜或收盤時間；若該日等於
    decision_date，契約無法證明日內先後。沒有另外的可驗證 policy 時，projector 必須拒絕投影。
    """

    def prepare_input(
        self,
        *,
        execution: RecommendationExecution,
        candidate_identities: tuple[CandidateIdentity, ...],
        rule_snapshot_refs: tuple[SnapshotReference, ...],
        mode: str,
    ) -> PreparedMLInput:
        """在明確排程的 prepare 階段解析並綁定輸入。"""
        ...


class PreparedMLProjector(Protocol[_ProjectionT]):
    """只接受已準備不可變契約的 ML build/inference 介面。

    實作須依已綁定的可得性、品質／缺件、資料範圍、隔離與權限狀態拒絕不安全投影。
    只有同日 available_date 時，若沒有可驗證的日內可得性政策，
    不得推定其早於 decision_at。
    """

    def project_prepared_input(
        self, prepared_input: PreparedMLInput, /
    ) -> _ProjectionT:
        """投影已準備的輸入；實作不得解析即時來源。"""
        ...


class PreparedMLRuntimeProjector(Protocol[_ProjectionT]):
    """R026 同次 runtime envelope 的一次性投影邊界。

    capability、owner/scope identity、feature facts、projection context 與 provenance
    都必須由單一不可變輸入取得；實作不得再接收外部 consumer 或查詢其他來源。
    """

    def project_prepared_runtime_input(
        self, runtime_input: PreparedMLRuntimeInputV1, /
    ) -> Mapping[str, _ProjectionT]:
        """消費同次 runtime input；成功或失敗後均不得重用其 capability。"""
        ...


__all__ = (
    "PreparedMLProjector",
    "PreparedMLRuntimeProjector",
    "RecommendationMLAdapter",
)
