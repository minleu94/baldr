"""以 Research Run Registry 已驗證資料讀回完整 portfolio DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal, TypeAlias

from app_module.recommendation.contracts import RecommendationExecution
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.replay_lineage import (
    ReplayLineageReadEnvelope,
    ReplayLineageSidecarV1,
)
from app_module.recommendation.replay_lineage_service import (
    verify_replay_lineage_children,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.recommendation_portfolio_result_artifact import (
    RecommendationPortfolioResultArtifactV1,
)
from app_module.research_run_service import ResearchRunData, ResearchRunService


class RecommendationPortfolioResultReadbackError(RuntimeError):
    """Registry 完整 portfolio DTO 或其 child lineage 無法安全讀回。"""


class PortfolioResultUnavailableReason(str, Enum):
    """不建立 partial DTO 時可回傳的具名 unavailable 原因。"""

    LEGACY_REGISTRY_RUN_WITHOUT_MARKER = "legacy_registry_run_without_portfolio_result_marker"


@dataclass(frozen=True, slots=True)
class PortfolioResultReadbackUnavailable:
    """舊 Registry run 可讀 metadata／Parquet，但沒有完整 DTO sidecar。"""

    registry_run_id: str
    reason: PortfolioResultUnavailableReason

    @property
    def status(self) -> Literal["unavailable"]:
        return "unavailable"


PortfolioResultReadback: TypeAlias = (
    RecommendationPortfolioBacktestResultDTO | PortfolioResultReadbackUnavailable
)


class RecommendationPortfolioResultReader:
    """只組裝已保存結果；不呼叫 replay/provider/backtest 計算。"""

    _MARKER = ResearchRunService.PORTFOLIO_RESULT_REQUIRED_MARKER
    _DESCRIPTOR = ResearchRunService.PORTFOLIO_RESULT_DESCRIPTOR_KEY

    def __init__(
        self,
        research_run_service: ResearchRunService,
        execution_persistence: RecommendationExecutionPersistence,
    ) -> None:
        self._research_run_service = research_run_service
        self._execution_persistence = execution_persistence

    def read(self, registry_run_id: str) -> PortfolioResultReadback:
        """從已驗證的 Registry envelope 組回 DTO，舊格式明示 unavailable。"""

        if (
            type(registry_run_id) is not str
            or not registry_run_id.strip()
            or registry_run_id != registry_run_id.strip()
        ):
            raise RecommendationPortfolioResultReadbackError(
                "registry_run_id 必須是非空白且無首尾空白的字串"
            )
        try:
            loaded = self._research_run_service.load_run_data(registry_run_id)
        except Exception as exc:
            raise RecommendationPortfolioResultReadbackError(
                "Research Run 已保存資料未通過完整性讀取"
            ) from exc
        try:
            return self._read_verified_data(registry_run_id, loaded)
        except RecommendationPortfolioResultReadbackError:
            raise
        except Exception as exc:
            raise RecommendationPortfolioResultReadbackError(
                "完整 portfolio DTO 或 replay child 驗證失敗"
            ) from exc

    def _read_verified_data(
        self,
        registry_run_id: str,
        loaded: ResearchRunData,
    ) -> PortfolioResultReadback:
        metadata = loaded.metadata
        if metadata.run_id != registry_run_id:
            raise RecommendationPortfolioResultReadbackError(
                "Registry metadata run_id 與查詢身分不一致"
            )
        if metadata.run_type != "recommendation_portfolio":
            raise RecommendationPortfolioResultReadbackError(
                "完整 portfolio reader 只接受 recommendation_portfolio run"
            )
        if type(metadata.data_manifest) is not dict:
            raise RecommendationPortfolioResultReadbackError(
                "Registry data_manifest 必須是 object"
            )

        manifest = metadata.data_manifest
        if self._MARKER not in manifest:
            if self._DESCRIPTOR in manifest or loaded.portfolio_result_artifact is not None:
                raise RecommendationPortfolioResultReadbackError(
                    "markerless Registry run 不得帶 portfolio result descriptor/artifact"
                )
            return PortfolioResultReadbackUnavailable(
                registry_run_id=registry_run_id,
                reason=PortfolioResultUnavailableReason.LEGACY_REGISTRY_RUN_WITHOUT_MARKER,
            )
        if manifest.get(self._MARKER) is not True:
            raise RecommendationPortfolioResultReadbackError(
                "portfolio result required marker 必須是 true"
            )

        artifact = loaded.portfolio_result_artifact
        if type(artifact) is not RecommendationPortfolioResultArtifactV1:
            raise RecommendationPortfolioResultReadbackError(
                "marked Registry run 缺少已驗證 portfolio result envelope"
            )
        descriptor = manifest.get(self._DESCRIPTOR)
        if type(descriptor) is not dict:
            raise RecommendationPortfolioResultReadbackError(
                "marked Registry run 缺少 portfolio result descriptor"
            )
        self._validate_artifact_binding(loaded, descriptor, artifact)

        result = artifact.materialize_result(
            equity_curve=loaded.equity,
            trades=loaded.trades,
            expected_registry_run_id=metadata.run_id,
            expected_portfolio_parent_id=artifact.portfolio_parent_id,
            equity_parquet_sha256=metadata.equity_parquet_hash,
            trades_parquet_sha256=metadata.trades_parquet_hash,
        )
        if result.replay_parent_id != artifact.portfolio_parent_id:
            raise RecommendationPortfolioResultReadbackError(
                "materialized portfolio parent identity 不一致"
            )

        snapshots_by_date = self._index_snapshots(
            result.snapshots,
            portfolio_parent_id=artifact.portfolio_parent_id,
        )
        lineage = loaded.replay_lineage
        if lineage is None:
            self._validate_lineage_status(
                manifest.get("replay_lineage_status"),
                portfolio_parent_id=artifact.portfolio_parent_id,
                expected_status="unavailable",
            )
            if any(snapshot.canonical_execution is not None for snapshot in result.snapshots):
                raise RecommendationPortfolioResultReadbackError(
                    "沒有 replay lineage 時不得附帶 canonical child execution"
                )
            return result

        if "replay_lineage_status" in manifest:
            self._validate_lineage_status(
                manifest["replay_lineage_status"],
                portfolio_parent_id=artifact.portfolio_parent_id,
                expected_status=None,
            )

        executions_by_date = self._verify_lineage(
            lineage,
            portfolio_parent_id=artifact.portfolio_parent_id,
            snapshots_by_date=snapshots_by_date,
        )

        # 僅在全批次 bytes/hash/日期/parent 均驗證後，依日期映射再附加 child。
        for snapshot_date, snapshot in snapshots_by_date.items():
            snapshot.attach_canonical_execution(executions_by_date[snapshot_date])
        return result

    @staticmethod
    def _validate_lineage_status(
        value: object,
        *,
        portfolio_parent_id: str,
        expected_status: str | None,
    ) -> None:
        if type(value) is not dict:
            raise RecommendationPortfolioResultReadbackError(
                "replay_lineage_status 必須是版本化 object"
            )
        if (
            type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
        ):
            raise RecommendationPortfolioResultReadbackError(
                "replay_lineage_status schema_version 不支援"
            )
        status = value.get("status")
        if type(status) is not str or status not in {"available", "unavailable"}:
            raise RecommendationPortfolioResultReadbackError(
                "replay_lineage_status status 無效"
            )
        if expected_status is not None and status != expected_status:
            raise RecommendationPortfolioResultReadbackError(
                f"replay_lineage_status 必須明示 {expected_status}"
            )
        if expected_status is None and status == "unavailable":
            raise RecommendationPortfolioResultReadbackError(
                "存在 replay lineage 時不得同時宣告 unavailable"
            )
        if value.get("parent_result_id") != portfolio_parent_id:
            raise RecommendationPortfolioResultReadbackError(
                "replay_lineage_status parent identity 與 portfolio 不一致"
            )

    @staticmethod
    def _validate_artifact_binding(
        loaded: ResearchRunData,
        descriptor: dict[object, object],
        artifact: RecommendationPortfolioResultArtifactV1,
    ) -> None:
        metadata = loaded.metadata
        expected = {
            "registry_run_id": metadata.run_id,
            "portfolio_parent_id": artifact.portfolio_parent_id,
            "raw_payload_sha256": artifact.raw_payload_sha256,
            "payload_hash": artifact.payload_hash,
            "equity_parquet_sha256": metadata.equity_parquet_hash,
            "trades_parquet_sha256": metadata.trades_parquet_hash,
        }
        if any(descriptor.get(key) != value for key, value in expected.items()):
            raise RecommendationPortfolioResultReadbackError(
                "已驗證 portfolio envelope 與 Registry descriptor/hash 不一致"
            )
        if (
            artifact.registry_run_id != metadata.run_id
            or artifact.equity_parquet_sha256 != metadata.equity_parquet_hash
            or artifact.trades_parquet_sha256 != metadata.trades_parquet_hash
        ):
            raise RecommendationPortfolioResultReadbackError(
                "portfolio envelope 與已解析 Parquet identity/hash 不一致"
            )

    @staticmethod
    def _canonical_snapshot_date(value: object, *, index: int) -> date:
        if type(value) is not str:
            raise RecommendationPortfolioResultReadbackError(
                f"snapshots[{index}].as_of_date 必須是 canonical ISO 日期字串"
            )
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise RecommendationPortfolioResultReadbackError(
                f"snapshots[{index}].as_of_date 不是有效 ISO 日期"
            ) from exc
        if parsed.isoformat() != value:
            raise RecommendationPortfolioResultReadbackError(
                f"snapshots[{index}].as_of_date 必須使用 YYYY-MM-DD canonical 格式"
            )
        return parsed

    @classmethod
    def _index_snapshots(
        cls,
        snapshots: list[RecommendationSnapshotDTO],
        *,
        portfolio_parent_id: str,
    ) -> dict[date, RecommendationSnapshotDTO]:
        indexed: dict[date, RecommendationSnapshotDTO] = {}
        for index, snapshot in enumerate(snapshots):
            if type(snapshot) is not RecommendationSnapshotDTO:
                raise RecommendationPortfolioResultReadbackError(
                    f"snapshots[{index}] DTO 型別錯誤"
                )
            snapshot_date = cls._canonical_snapshot_date(
                snapshot.as_of_date, index=index
            )
            if snapshot_date in indexed:
                raise RecommendationPortfolioResultReadbackError(
                    "portfolio snapshots 不可有重複日期"
                )
            if snapshot.replay_parent_id != portfolio_parent_id:
                raise RecommendationPortfolioResultReadbackError(
                    f"snapshots[{index}] replay parent 與 portfolio 不一致"
                )
            if snapshot.canonical_execution is not None:
                raise RecommendationPortfolioResultReadbackError(
                    f"snapshots[{index}] decoded DTO 不應預先帶 canonical child"
                )
            indexed[snapshot_date] = snapshot
        return indexed

    def _verify_lineage(
        self,
        envelope: ReplayLineageReadEnvelope,
        *,
        portfolio_parent_id: str,
        snapshots_by_date: dict[date, RecommendationSnapshotDTO],
    ) -> dict[date, RecommendationExecution]:
        if type(envelope) is not ReplayLineageReadEnvelope:
            raise RecommendationPortfolioResultReadbackError(
                "Registry replay lineage envelope 型別錯誤"
            )
        sidecar = envelope.sidecar
        if type(sidecar) is not ReplayLineageSidecarV1:
            raise RecommendationPortfolioResultReadbackError(
                "Registry replay lineage sidecar 型別錯誤"
            )
        if sidecar.parent_result_id != portfolio_parent_id:
            raise RecommendationPortfolioResultReadbackError(
                "replay lineage parent 與 portfolio parent 不一致"
            )

        children_by_date = {}
        for child in sidecar.children:
            if child.snapshot_date in children_by_date:
                raise RecommendationPortfolioResultReadbackError(
                    "replay lineage child 日期不可重複"
                )
            if child.replay_parent_ref.reference_id != portfolio_parent_id:
                raise RecommendationPortfolioResultReadbackError(
                    "child REPLAY_PARENT reference 與 portfolio parent 不一致"
                )
            children_by_date[child.snapshot_date] = child
        if set(children_by_date) != set(snapshots_by_date):
            raise RecommendationPortfolioResultReadbackError(
                "replay lineage child 日期集合必須精確符合 portfolio snapshots"
            )

        verified = verify_replay_lineage_children(envelope, self._execution_persistence)
        if len(verified) != len(sidecar.children):
            raise RecommendationPortfolioResultReadbackError(
                "已驗證 child 數量與 replay lineage 不一致"
            )
        child_by_id = {child.result_id: child for child in sidecar.children}
        executions_by_date: dict[date, RecommendationExecution] = {}
        seen_result_ids: set[str] = set()
        for execution in verified:
            if type(execution) is not RecommendationExecution:
                raise RecommendationPortfolioResultReadbackError(
                    "child artifact 解碼結果型別錯誤"
                )
            if execution.result_id in seen_result_ids:
                raise RecommendationPortfolioResultReadbackError(
                    "已驗證 child result_id 重複"
                )
            seen_result_ids.add(execution.result_id)
            matched_child = child_by_id.get(execution.result_id)
            if matched_child is None:
                raise RecommendationPortfolioResultReadbackError(
                    "已驗證 child 不在 Registry replay lineage 中"
                )
            snapshot_date = matched_child.snapshot_date
            if execution.context.as_of_date != snapshot_date:
                raise RecommendationPortfolioResultReadbackError(
                    "child context 日期與 replay lineage 不一致"
                )
            if snapshot_date in executions_by_date:
                raise RecommendationPortfolioResultReadbackError(
                    "已驗證 child 日期重複"
                )
            executions_by_date[snapshot_date] = execution
        if set(executions_by_date) != set(snapshots_by_date):
            raise RecommendationPortfolioResultReadbackError(
                "已驗證 child 日期集合必須精確符合 snapshots"
            )
        return executions_by_date


__all__ = (
    "PortfolioResultReadback",
    "PortfolioResultReadbackUnavailable",
    "PortfolioResultUnavailableReason",
    "RecommendationPortfolioResultReadbackError",
    "RecommendationPortfolioResultReader",
)
