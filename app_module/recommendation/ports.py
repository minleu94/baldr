"""Recommendation persistence 的狹義 I/O ports。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ArtifactIndexRecord,
    StoredArtifact,
)


class ResultArtifactStorePort(Protocol):
    """app adapter 可使用的低階 bytes/hash/index metadata seam。"""

    def artifact_name_for(self, result_id: str) -> str: ...

    def read_artifact(self, result_id: str) -> bytes | None: ...

    def publish_artifact(
        self, payload: bytes, metadata: ArtifactIndexMetadata
    ) -> Path: ...

    def get_index(self, result_id: str) -> ArtifactIndexRecord | None: ...

    def get_identity_payload_hash(self, result_id: str) -> str | None: ...

    def has_legacy_run(self, result_id: str) -> bool: ...

    def list_index_records(self) -> tuple[ArtifactIndexRecord, ...]: ...

    def index_artifact(
        self,
        metadata: ArtifactIndexMetadata,
        *,
        repair_projection: bool = False,
    ) -> ArtifactIndexRecord: ...

    def iter_artifacts(self) -> Iterable[StoredArtifact]: ...

    def rebuild_index_projection(
        self, entries: Iterable[tuple[bytes, ArtifactIndexMetadata]]
    ) -> tuple[ArtifactIndexRecord, ...]: ...

    def rename(self, result_id: str, label: str) -> ArtifactIndexRecord: ...

    def update_notes(self, result_id: str, notes: str) -> ArtifactIndexRecord: ...

    def restore_missing_metadata(
        self, metadata: ArtifactIndexMetadata
    ) -> ArtifactIndexRecord: ...


__all__ = ("ResultArtifactStorePort",)
