"""RecommendationExecution codec 與 create-only artifact persistence adapter。"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Callable, Iterator

from app_module.recommendation.codec import (
    ExecutionCodecError,
    ExecutionReadEnvelope,
    decode_execution_envelope,
    encode_execution,
)
from app_module.recommendation.contracts import (
    EXECUTION_SCHEMA_REVISION,
    ExecutionStatus,
    IndexStatus,
    RecommendationExecution,
    SaveReceipt,
    schema_version,
)
from app_module.recommendation.ports import ResultArtifactStorePort
from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ArtifactIndexRecord,
    ResultArtifactConflict,
    ResultArtifactIndexError,
    ResultArtifactIntegrityError,
    ResultArtifactPostPublishIndexError,
    ResultArtifactPublishError,
    ResultArtifactStoreError,
)


class ExecutionPersistenceError(RuntimeError):
    """應用層保存錯誤基底。"""


class ExecutionIdentityConflict(ExecutionPersistenceError):
    """同一 result_id 已綁定不同 canonical payload hash。"""


class ExecutionArtifactWriteError(ExecutionPersistenceError):
    """immutable artifact 無法安全 create-only 發布。"""


class ExecutionIndexReadError(ExecutionPersistenceError):
    """SQLite identity/query projection 無法讀取。"""


class ExecutionIndexRebuildError(ExecutionPersistenceError):
    """SQLite index projection rebuild 無法完成；immutable artifact 未被改寫。"""


class PartialExecutionPersistenceError(ExecutionPersistenceError):
    """artifact 已 durable，但 SQLite index 尚待相同 ID/hash 重試。"""

    def __init__(self, receipt: SaveReceipt, cause: BaseException) -> None:
        super().__init__(
            "artifact 已發布；SQLite index 未完成，請以相同 result_id/payload_hash 重試"
        )
        self.receipt = receipt
        self.__cause__ = cause


class ExecutionArtifactIntegrityError(ExecutionPersistenceError):
    """bytes、identity、hash 或 schema 與 immutable index 不符。"""


class ExecutionMetadataError(ExecutionPersistenceError):
    """execution index 存在，但其可變 metadata 讀寫不完整。"""


def _decode_canonical_execution(
    raw_payload: bytes, *, expected_result_id: str | None = None
) -> ExecutionReadEnvelope:
    try:
        envelope = decode_execution_envelope(raw_payload)
    except ExecutionCodecError as exc:
        raise ExecutionArtifactIntegrityError("execution artifact codec 驗證失敗") from exc
    if (
        expected_result_id is not None
        and envelope.execution.result_id != expected_result_id
    ):
        raise ExecutionArtifactIntegrityError(
            "artifact 內 result_id 與 opaque index identity 不符"
        )
    return envelope


def _receipt_time(value: str | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ExecutionArtifactIntegrityError("SQLite persisted_at 不是 ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionArtifactIntegrityError("SQLite persisted_at 缺少 timezone offset")
    return parsed


class RecommendationExecutionPersistence:
    """將 typed execution 經 codec 封存，再交由 data leaf 發布與索引。"""

    def __init__(self, store: ResultArtifactStorePort) -> None:
        self._store = store

    @staticmethod
    def _now_utc(now: Callable[[], datetime]) -> datetime:
        value = now()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("保存時鐘必須回傳 timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _metadata(
        self,
        execution: RecommendationExecution,
        payload_hash: str,
        artifact_hash: str,
        *,
        label: str,
        notes: str,
        persisted_at: str,
    ) -> ArtifactIndexMetadata:
        return ArtifactIndexMetadata(
            result_id=execution.result_id,
            payload_hash=payload_hash,
            artifact_sha256=artifact_hash,
            schema_version=schema_version,
            schema_revision=EXECUTION_SCHEMA_REVISION,
            label=label,
            notes=notes,
            persisted_at=persisted_at,
        )

    def _validate_existing_index(
        self,
        record: ArtifactIndexRecord | None,
        metadata: ArtifactIndexMetadata,
    ) -> None:
        if record is None:
            return
        old = record.metadata
        if old.result_id != metadata.result_id or old.payload_hash != metadata.payload_hash:
            raise ExecutionIdentityConflict(
                "同一 result_id 已保存不同 payload_hash；拒絕覆寫"
            )
        if (
            old.schema_version != metadata.schema_version
            or old.schema_revision != metadata.schema_revision
        ):
            raise ExecutionIdentityConflict(
                "同一 result_id 的 schema identity 不同；拒絕覆寫"
            )
        if old.artifact_sha256 != metadata.artifact_sha256:
            raise ExecutionArtifactIntegrityError(
                "canonical payload hash 相同但 raw artifact bytes/hash 不同"
            )

    def save(
        self,
        execution: RecommendationExecution,
        *,
        label: str | None = None,
        notes: str | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> SaveReceipt:
        """create-only 保存；異 hash conflict，file-only orphan 可安全補索引。"""

        if type(execution) is not RecommendationExecution:
            raise TypeError("新 writer 僅接受 RecommendationExecution")
        if execution.status is not ExecutionStatus.COMPLETED:
            raise ValueError("一般推薦保存僅接受 completed execution")
        raw_payload = encode_execution(execution)
        envelope = _decode_canonical_execution(
            raw_payload, expected_result_id=execution.result_id
        )
        if envelope.schema_revision != EXECUTION_SCHEMA_REVISION:
            raise ExecutionArtifactIntegrityError(
                "新 writer 只能發布目前 canonical execution revision"
            )
        if envelope.execution != execution:
            raise ExecutionArtifactIntegrityError("encode/decode execution identity 不一致")
        payload_hash = envelope.payload_hash
        artifact_hash = envelope.raw_payload_sha256
        timestamp = self._now_utc(now)
        metadata = self._metadata(
            execution,
            payload_hash,
            artifact_hash,
            label=execution.result_id if label is None else label,
            notes="" if notes is None else notes,
            persisted_at=timestamp.isoformat(timespec="microseconds"),
        )

        try:
            legacy_identity_exists = self._store.has_legacy_run(execution.result_id)
            metadata_identity_hash = self._store.get_identity_payload_hash(
                execution.result_id
            )
            existing_index = self._store.get_index(execution.result_id)
        except (ResultArtifactIndexError, sqlite3.Error) as exc:
            raise ExecutionIndexReadError(
                "無法讀取保存前的 SQLite identity；尚未發布 artifact"
            ) from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查保存前的 artifact identity"
            ) from exc
        if legacy_identity_exists:
            raise ExecutionIdentityConflict(
                "同一 result_id 已由 legacy runs namespace 使用"
            )
        if metadata_identity_hash is not None and metadata_identity_hash != payload_hash:
            raise ExecutionIdentityConflict(
                "mutable metadata authority 已將此 result_id 綁定不同 payload_hash"
            )

        try:
            self._validate_existing_index(existing_index, metadata)
            existing_bytes = self._store.read_artifact(execution.result_id)
            if existing_bytes is not None:
                existing_envelope = _decode_canonical_execution(
                    existing_bytes, expected_result_id=execution.result_id
                )
                existing_payload_hash = existing_envelope.payload_hash
                existing_artifact_hash = existing_envelope.raw_payload_sha256
                if existing_payload_hash != payload_hash:
                    raise ExecutionIdentityConflict(
                        "相同 result_id 的 orphan artifact 有不同 payload_hash；拒絕覆寫"
                    )
                if existing_artifact_hash != artifact_hash or existing_bytes != raw_payload:
                    raise ExecutionArtifactIntegrityError(
                        "相同 payload_hash 的既有 artifact bytes 不同；拒絕覆寫"
                    )
            self._store.publish_artifact(raw_payload, metadata)
        except (ExecutionIdentityConflict, ExecutionArtifactIntegrityError):
            raise
        except ResultArtifactConflict as exc:
            raise ExecutionIdentityConflict(str(exc)) from exc
        except ResultArtifactPostPublishIndexError as exc:
            receipt = SaveReceipt(
                result_id=execution.result_id,
                payload_hash=payload_hash,
                artifact_location=str(self._store.artifact_name_for(execution.result_id)),
                persisted_at=timestamp,
                index_status=IndexStatus.PENDING,
            )
            raise PartialExecutionPersistenceError(receipt, exc) from exc
        except ResultArtifactIndexError as exc:
            raise ExecutionIndexReadError(
                "artifact 尚未發布；SQLite identity lock 無法建立"
            ) from exc
        except (ResultArtifactPublishError, OSError) as exc:
            raise ExecutionArtifactWriteError("推薦 execution artifact 發布失敗") from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError("推薦 execution artifact 檢查失敗") from exc

        try:
            record = self._store.index_artifact(metadata)
            if record.metadata.persisted_at is None or record.metadata.label is None or record.metadata.notes is None:
                record = self._store.restore_missing_metadata(metadata)
        except ResultArtifactConflict as exc:
            raise ExecutionIdentityConflict(str(exc)) from exc
        except ResultArtifactIntegrityError as exc:
            raise ExecutionArtifactIntegrityError("推薦 execution index integrity 失敗") from exc
        except (ResultArtifactIndexError, sqlite3.Error) as exc:
            receipt = SaveReceipt(
                result_id=execution.result_id,
                payload_hash=payload_hash,
                artifact_location=str(self._store.artifact_name_for(execution.result_id)),
                persisted_at=timestamp,
                index_status=IndexStatus.PENDING,
            )
            raise PartialExecutionPersistenceError(receipt, exc) from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError("推薦 execution index 驗證失敗") from exc

        persisted_at = _receipt_time(record.metadata.persisted_at, timestamp)
        return SaveReceipt(
            result_id=execution.result_id,
            payload_hash=payload_hash,
            artifact_location=record.artifact_name,
            persisted_at=persisted_at,
            index_status=IndexStatus.INDEXED,
        )

    def rebuild_index(self) -> tuple[str, ...]:
        """從驗證過的 immutable artifacts 重建缺失／錯誤 projection。

        可變 metadata table 是獨立權威。若整個 SQLite database 遺失，重建只會
        產生空 metadata 欄位；本方法不以檔案時間或當前 service 狀態猜值。
        """

        result_ids: list[str] = []

        def validated_inventory() -> Iterator[tuple[bytes, ArtifactIndexMetadata]]:
            try:
                for artifact in self._store.iter_artifacts():
                    envelope = _decode_canonical_execution(
                        artifact.payload
                    )
                    execution = envelope.execution
                    expected_name = self._store.artifact_name_for(execution.result_id)
                    if artifact.artifact_name != expected_name:
                        raise ExecutionArtifactIntegrityError(
                            "artifact filename 與內部 opaque result_id mapping 不符"
                        )
                    metadata = ArtifactIndexMetadata(
                        result_id=execution.result_id,
                        payload_hash=envelope.payload_hash,
                        artifact_sha256=envelope.raw_payload_sha256,
                        schema_version=envelope.schema_version,
                        schema_revision=envelope.schema_revision,
                        label=None,
                        notes=None,
                        persisted_at=None,
                    )
                    result_ids.append(metadata.result_id)
                    yield artifact.payload, metadata
            except (ExecutionArtifactIntegrityError, ExecutionIndexRebuildError):
                raise
            except ResultArtifactConflict as exc:
                raise ExecutionIdentityConflict(
                    "artifact inventory 與既有 result_id identity 衝突"
                ) from exc
            except ResultArtifactIndexError as exc:
                raise ExecutionIndexRebuildError(
                    "artifact inventory 階段的 store SQLite 操作失敗"
                ) from exc
            except ResultArtifactIntegrityError as exc:
                raise ExecutionArtifactIntegrityError(
                    "artifact inventory 完整性驗證失敗"
                ) from exc
            except ResultArtifactStoreError as exc:
                raise ExecutionArtifactIntegrityError(
                    "artifact inventory store 操作失敗"
                ) from exc
            except OSError as exc:
                raise ExecutionArtifactIntegrityError(
                    "artifact inventory 檔案 I/O 失敗"
                ) from exc

        try:
            self._store.rebuild_index_projection(validated_inventory())
        except (ExecutionArtifactIntegrityError, ExecutionIndexRebuildError, ExecutionIdentityConflict):
            raise
        except ResultArtifactConflict as exc:
            raise ExecutionIdentityConflict(
                "artifact inventory 與 SQLite identity authority 衝突"
            ) from exc
        except ResultArtifactIndexError as exc:
            raise ExecutionIndexRebuildError(
                "SQLite execution index projection 重建失敗"
            ) from exc
        except sqlite3.Error as exc:
            raise ExecutionIndexRebuildError(
                "SQLite execution index projection 重建失敗"
            ) from exc
        except ResultArtifactIntegrityError as exc:
            raise ExecutionArtifactIntegrityError(
                "execution artifact inventory/rebuild integrity 失敗"
            ) from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError(
                "execution artifact inventory/rebuild store 操作失敗"
            ) from exc
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "execution artifact inventory/rebuild 檔案 I/O 失敗"
            ) from exc
        return tuple(result_ids)

    def rename(self, result_id: str, label: str) -> ArtifactIndexRecord:
        """只改 mutable metadata；先驗證目前 artifact，不觸碰其 bytes。"""

        record, _ = self.read_verified(result_id)
        try:
            return self._store.rename(record.metadata.result_id, label)
        except ResultArtifactStoreError as exc:
            raise ExecutionMetadataError("execution label 更新失敗") from exc

    def update_notes(self, result_id: str, notes: str) -> ArtifactIndexRecord:
        record, _ = self.read_verified(result_id)
        try:
            return self._store.update_notes(record.metadata.result_id, notes)
        except ResultArtifactStoreError as exc:
            raise ExecutionMetadataError("execution notes 更新失敗") from exc

    def read_verified(
        self, result_id: str
    ) -> tuple[ArtifactIndexRecord, RecommendationExecution]:
        record, envelope = self.read_verified_envelope(result_id)
        return record, envelope.execution

    def read_verified_envelope(
        self, result_id: str
    ) -> tuple[ArtifactIndexRecord, ExecutionReadEnvelope]:
        """讀取並保留 artifact 原始 header revision、bytes 與 hash。"""

        try:
            record = self._store.get_index(result_id)
            if record is None:
                raise KeyError(result_id)
            raw_payload = self._store.read_artifact(result_id)
        except KeyError:
            raise
        except ResultArtifactIndexError as exc:
            raise ExecutionIndexReadError("無法讀取 execution SQLite index") from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError("讀取 execution index/artifact 失敗") from exc
        if raw_payload is None:
            raise ExecutionArtifactIntegrityError(
                "execution index 指向缺失 artifact；結果不可用"
            )
        envelope = _decode_canonical_execution(
            raw_payload, expected_result_id=result_id
        )
        metadata = record.metadata
        if (
            metadata.payload_hash != envelope.payload_hash
            or metadata.artifact_sha256 != envelope.raw_payload_sha256
            or metadata.schema_version != envelope.schema_version
            or metadata.schema_revision != envelope.schema_revision
        ):
            raise ExecutionArtifactIntegrityError(
                "execution index 與 canonical artifact hash/schema 不符"
            )
        expected_name = self._store.artifact_name_for(result_id)
        if record.artifact_name != expected_name:
            raise ExecutionArtifactIntegrityError("execution index artifact path 不可信")
        return record, envelope

    def list_verified_envelopes(
        self,
    ) -> tuple[tuple[ArtifactIndexRecord, ExecutionReadEnvelope], ...]:
        """列出 canonical artifact，並保留每筆來源 envelope metadata。"""

        try:
            records = self._store.list_index_records()
        except ResultArtifactIndexError as exc:
            raise ExecutionIndexReadError("無法列出 execution SQLite index") from exc
        except ResultArtifactStoreError as exc:
            raise ExecutionArtifactIntegrityError("列出 execution index 失敗") from exc
        verified: list[tuple[ArtifactIndexRecord, ExecutionReadEnvelope]] = []
        for record in records:
            verified.append(self.read_verified_envelope(record.metadata.result_id))
        return tuple(verified)

    def list_verified(
        self,
    ) -> tuple[tuple[ArtifactIndexRecord, RecommendationExecution], ...]:
        """回傳每筆都已通過 artifact/hash/schema/identity 的索引投影。"""

        return tuple(
            (record, envelope.execution)
            for record, envelope in self.list_verified_envelopes()
        )


__all__ = (
    "ExecutionArtifactIntegrityError",
    "ExecutionArtifactWriteError",
    "ExecutionIndexReadError",
    "ExecutionIndexRebuildError",
    "ExecutionIdentityConflict",
    "ExecutionMetadataError",
    "ExecutionPersistenceError",
    "PartialExecutionPersistenceError",
    "RecommendationExecutionPersistence",
)
