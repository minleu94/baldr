"""Research Run Registry service for immutable metadata and Parquet payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from copy import deepcopy
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import stat
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from app_module.factor_service import FactorService
from app_module.recommendation.replay_lineage import (
    REPLAY_LINEAGE_SCHEMA_REVISION,
    REPLAY_LINEAGE_SCHEMA_VERSION,
    ReplayLineageCodecError,
    ReplayLineageReadEnvelope,
    ReplayLineageSidecarV1,
    decode_replay_lineage_envelope,
    encode_replay_lineage,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError,
    RecommendationPortfolioResultArtifactV1,
    decode_portfolio_result_artifact,
    encode_portfolio_result_artifact,
)
from app_module.research_run_dtos import (
    ResearchRunMetadataDTO,
    canonical_json,
    normalize_research_run_json_value,
)
from app_module.research_run_repository import (
    ResearchRunConflictError,
    ResearchRunRepository,
    ResearchRunRepositoryError,
)
from decision_module.factors.factor_dtos import FactorRecord


class ResearchRunServiceError(Exception):
    """Research Run Service 基底例外。"""


class ResearchRunIntegrityError(ResearchRunServiceError):
    """Research Run payload hash、sidecar 或 registry metadata 不一致。"""


class PromotedResearchRunArchiveError(ResearchRunServiceError):
    """已升級策略版本的 run 不可封存。"""


class InjectedResearchRunFailure(ResearchRunServiceError):
    """測試用注入式崩潰點。"""


@dataclass(frozen=True)
class ResearchRunData:
    metadata: ResearchRunMetadataDTO
    equity: pd.DataFrame
    trades: pd.DataFrame
    replay_lineage: ReplayLineageReadEnvelope | None = None
    portfolio_result_artifact: RecommendationPortfolioResultArtifactV1 | None = None


class ResearchRunService:
    """Research Run Registry 唯一寫入 owner。

    SQLite 與 filesystem 沒有共同 transaction；本服務使用 staging 狀態與
    顯式 reconciliation 來避免半成品被當成完整 run 載入。建構與查詢不寫入。
    """

    REPLAY_LINEAGE_MANIFEST_KEY = "replay_lineage_sidecar"
    PORTFOLIO_RESULT_REQUIRED_MARKER = ResearchRunRepository.PORTFOLIO_RESULT_REQUIRED_MARKER
    PORTFOLIO_RESULT_DESCRIPTOR_KEY = ResearchRunRepository.PORTFOLIO_RESULT_DESCRIPTOR_KEY
    _PORTFOLIO_RESULT_DESCRIPTOR_KEYS = ResearchRunRepository.PORTFOLIO_RESULT_DESCRIPTOR_KEYS
    _REPLAY_LINEAGE_DESCRIPTOR_KEYS = frozenset(
        {
            "schema_version",
            "schema_revision",
            "parent_result_id",
            "relative_path",
            "raw_payload_sha256",
            "payload_hash",
            "child_count",
        }
    )

    def __init__(self, config: Any):
        self.config = config
        self.repository = ResearchRunRepository(config)
        self.parquet_dir = Path(config.research_run_parquet_dir)
        self.staging_dir = Path(config.research_run_staging_dir)

    def save_run(
        self,
        metadata: ResearchRunMetadataDTO,
        equity: pd.DataFrame,
        trades: pd.DataFrame,
        *,
        factor_records: list[FactorRecord] | None = None,
        factor_decision_date: date | None = None,
        factor_snapshot: dict[str, Any] | None = None,
        factor_contributions: dict[str, Any] | None = None,
        replay_lineage_sidecar: ReplayLineageSidecarV1 | None = None,
        portfolio_result: RecommendationPortfolioBacktestResultDTO | None = None,
        fail_at: str | None = None,
    ) -> ResearchRunMetadataDTO:
        metadata = deepcopy(metadata)
        equity = self._parquet_frame_copy(equity)
        trades = self._parquet_frame_copy(trades)
        metadata = self._metadata_with_factor_manifest(
            metadata,
            factor_records=factor_records,
            factor_decision_date=factor_decision_date,
            factor_snapshot=factor_snapshot,
            factor_contributions=factor_contributions,
        )
        metadata = self._metadata_with_execution_contract(metadata)
        paths = self._paths_for(metadata.run_id)
        replay_lineage_bytes: bytes | None = None
        if replay_lineage_sidecar is not None:
            try:
                replay_lineage_bytes = encode_replay_lineage(replay_lineage_sidecar)
                envelope = decode_replay_lineage_envelope(replay_lineage_bytes)
            except (ReplayLineageCodecError, TypeError, ValueError) as exc:
                raise ResearchRunIntegrityError("replay lineage sidecar contract 無效") from exc
            metadata = self._metadata_with_replay_lineage(metadata, envelope, paths)
        elif self.REPLAY_LINEAGE_MANIFEST_KEY in metadata.data_manifest:
            raise ResearchRunIntegrityError(
                "metadata 宣告 replay lineage sidecar，但 save_run 未提供 sidecar bytes"
            )
        if portfolio_result is not None:
            portfolio_parent_id = self._portfolio_parent_id(portfolio_result)
            self._validate_portfolio_lineage_status(
                metadata,
                portfolio_parent_id=portfolio_parent_id,
                has_lineage_sidecar=replay_lineage_sidecar is not None,
            )
            metadata = self._metadata_with_portfolio_marker(
                metadata, portfolio_result, equity=equity, trades=trades
            )
            if replay_lineage_sidecar is not None and (
                replay_lineage_sidecar.parent_result_id != portfolio_parent_id
            ):
                raise ResearchRunIntegrityError(
                    "portfolio result 與 replay lineage sidecar parent 不一致"
                )
        elif (
            self.PORTFOLIO_RESULT_REQUIRED_MARKER in metadata.data_manifest
            or self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in metadata.data_manifest
        ):
            raise ResearchRunIntegrityError(
                "metadata 宣告 portfolio result sidecar，但 save_run 未提供完整 DTO"
            )
        self.repository.ensure_schema()
        existing_raw = self.repository.get_raw_metadata_row(metadata.run_id)
        if existing_raw:
            existing = self.repository.get_metadata(metadata.run_id)
            if portfolio_result is not None:
                return self._return_existing_portfolio_result(
                    existing_raw=existing_raw,
                    existing=existing,
                    base_metadata=metadata,
                    result=portfolio_result,
                    equity=equity,
                    trades=trades,
                    replay_lineage_bytes=replay_lineage_bytes,
                )
            if existing and existing.payload_hash != metadata.payload_hash:
                raise ResearchRunConflictError(
                    f"run_id 已存在但 payload_hash 不一致: {metadata.run_id}"
                )
            if existing_raw["storage_state"] == "committed":
                saved = self.load_run_data(metadata.run_id)
                if (
                    self._immutable_metadata(saved.metadata) != self._immutable_metadata(metadata)
                    or not saved.equity.equals(equity.reset_index(drop=True))
                    or not saved.trades.equals(trades.reset_index(drop=True))
                    or (
                        saved.replay_lineage.raw_payload
                        if saved.replay_lineage is not None
                        else None
                    ) != replay_lineage_bytes
                ):
                    raise ResearchRunConflictError("宣告 hash 相同但實際保存內容不同")
                return saved.metadata
            raise ResearchRunIntegrityError(f"run 尚未完整提交: {metadata.run_id}")

        if portfolio_result is not None:
            self._assert_portfolio_paths_unclaimed(paths)
        elif (
            paths["portfolio_result_temp"].exists()
            or paths["portfolio_result_final"].exists()
            or self._is_symlink_or_reparse_point(paths["portfolio_result_temp"])
            or self._is_symlink_or_reparse_point(paths["portfolio_result_final"])
        ):
            raise ResearchRunConflictError(
                "portfolio result orphan sidecar bytes 已存在；拒絕 markerless save"
            )

        self._fail_if_requested(fail_at, "before_temp_write")

        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.repository.insert_metadata(metadata, staging=True)
        self._fail_if_requested(fail_at, "after_staging_row")

        if portfolio_result is None:
            equity.to_parquet(paths["equity_temp"], index=False)
            trades.to_parquet(paths["trades_temp"], index=False)
        else:
            self._write_parquet_temp_create_only(equity, paths["equity_temp"])
            self._write_parquet_temp_create_only(trades, paths["trades_temp"])
        if replay_lineage_bytes is not None:
            self._write_replay_lineage_temp(
                paths["replay_lineage_temp"], replay_lineage_bytes
            )
            self._fail_if_requested(fail_at, "after_replay_lineage_temp_write")
        self._fail_if_requested(fail_at, "after_temp_write")

        equity_hash = self._sha256_file(paths["equity_temp"])
        trades_hash = self._sha256_file(paths["trades_temp"])
        committed_metadata = replace(
            metadata,
            equity_path=str(paths["equity_final"]),
            equity_parquet_hash=equity_hash,
            trades_path=str(paths["trades_final"]),
            trades_parquet_hash=trades_hash,
        )
        if portfolio_result is not None:
            artifact = self._encode_portfolio_result(
                portfolio_result,
                registry_run_id=metadata.run_id,
                portfolio_parent_id=self._portfolio_parent_id(portfolio_result),
                equity_parquet_sha256=equity_hash,
                trades_parquet_sha256=trades_hash,
            )
            self._write_bytes_create_only(
                paths["portfolio_result_temp"], artifact.raw_payload
            )
            self._fail_if_requested(fail_at, "after_portfolio_result_temp_write")
            try:
                decoded_temp = decode_portfolio_result_artifact(
                    paths["portfolio_result_temp"].read_bytes()
                )
            except (OSError, PortfolioResultArtifactCodecError, TypeError, ValueError) as exc:
                raise ResearchRunIntegrityError(
                    "portfolio result staging sidecar 無法重新驗證"
                ) from exc
            if decoded_temp != artifact:
                raise ResearchRunIntegrityError(
                    "portfolio result staging sidecar 與剛編碼 envelope 不一致"
                )
            finalized_metadata = self._metadata_with_portfolio_descriptor(
                committed_metadata, artifact, paths
            )
            self.repository.finalize_portfolio_result_staging(
                metadata.run_id,
                expected_payload_hash=metadata.payload_hash,
                finalized_metadata=finalized_metadata,
            )
            self._fail_if_requested(fail_at, "after_portfolio_result_finalize")
            self._verify_marked_parquet_temp(finalized_metadata, paths)
            self._validate_portfolio_result_file(
                finalized_metadata,
                paths["portfolio_result_temp"],
                expected_path=paths["portfolio_result_temp"],
            )
            self.repository.mark_portfolio_result_files_ready(
                metadata.run_id,
                expected_payload_hash=finalized_metadata.payload_hash,
                expected_data_manifest=finalized_metadata.data_manifest,
            )
            self._fail_if_requested(fail_at, "after_hash")

            self._publish_bytes_create_only(
                paths["equity_temp"],
                paths["equity_final"],
                expected_hash=equity_hash,
            )
            self._fail_if_requested(fail_at, "after_first_rename")
            self._publish_bytes_create_only(
                paths["trades_temp"],
                paths["trades_final"],
                expected_hash=trades_hash,
            )
            self._fail_if_requested(fail_at, "after_second_rename")
            self._publish_bytes_create_only(
                paths["portfolio_result_temp"],
                paths["portfolio_result_final"],
                expected_hash=artifact.raw_payload_sha256,
            )
            self._fail_if_requested(fail_at, "after_portfolio_result_rename")
            if replay_lineage_bytes is not None:
                self._publish_replay_lineage(
                    finalized_metadata,
                    paths["replay_lineage_temp"],
                    paths["replay_lineage_final"],
                )
                self._fail_if_requested(fail_at, "after_replay_lineage_rename")
            self._fail_if_requested(fail_at, "before_final_commit")

            final_equity_bytes, final_trades_bytes = self._verify_marked_parquet_final(
                finalized_metadata, paths
            )
            self._parse_portfolio_parquet_bytes(
                final_equity_bytes, final_trades_bytes
            )
            final_artifact = self._read_portfolio_result_file(
                finalized_metadata,
                paths["portfolio_result_final"],
                expected_path=paths["portfolio_result_final"],
            )
            if final_artifact.raw_payload != artifact.raw_payload:
                raise ResearchRunIntegrityError(
                    "published portfolio result bytes 與 staging bytes 不一致"
                )
            if replay_lineage_bytes is not None:
                self._read_replay_lineage_file(
                    finalized_metadata, paths["replay_lineage_final"]
                )
            self.repository.mark_portfolio_result_committed(
                metadata.run_id,
                expected_payload_hash=finalized_metadata.payload_hash,
                expected_data_manifest=finalized_metadata.data_manifest,
            )
            return finalized_metadata

        self.repository.update_storage_fields(
            metadata.run_id,
            equity_path=committed_metadata.equity_path,
            equity_parquet_hash=equity_hash,
            trades_path=committed_metadata.trades_path,
            trades_parquet_hash=trades_hash,
            storage_state="files_ready",
            integrity_status="pending",
        )
        self._fail_if_requested(fail_at, "after_hash")

        os.replace(paths["equity_temp"], paths["equity_final"])
        self._fail_if_requested(fail_at, "after_first_rename")
        os.replace(paths["trades_temp"], paths["trades_final"])
        self._fail_if_requested(fail_at, "after_second_rename")
        if replay_lineage_bytes is not None:
            self._publish_replay_lineage(
                metadata,
                paths["replay_lineage_temp"],
                paths["replay_lineage_final"],
            )
            self._fail_if_requested(fail_at, "after_replay_lineage_rename")
        self._fail_if_requested(fail_at, "before_final_commit")

        self.repository.update_storage_fields(
            metadata.run_id,
            storage_state="committed",
            integrity_status="valid",
        )
        return committed_metadata

    @staticmethod
    def _portfolio_parent_id(
        result: RecommendationPortfolioBacktestResultDTO,
    ) -> str:
        try:
            parent_id = result.replay_parent_id
        except (TypeError, ValueError) as exc:
            raise ResearchRunIntegrityError(
                "portfolio result replay parent identity 不一致"
            ) from exc
        if type(parent_id) is not str or not parent_id.strip() or parent_id != parent_id.strip():
            raise ResearchRunIntegrityError(
                "portfolio result 必須帶有明確 replay parent identity"
            )
        return parent_id

    def _metadata_with_portfolio_marker(
        self,
        metadata: ResearchRunMetadataDTO,
        result: RecommendationPortfolioBacktestResultDTO,
        *,
        equity: pd.DataFrame,
        trades: pd.DataFrame,
    ) -> ResearchRunMetadataDTO:
        if metadata.run_type != "recommendation_portfolio":
            raise ResearchRunIntegrityError(
                "完整 portfolio result 只可附加到 recommendation_portfolio run"
            )
        if type(result) is not RecommendationPortfolioBacktestResultDTO:
            raise ResearchRunIntegrityError(
                "portfolio_result 必須是 RecommendationPortfolioBacktestResultDTO"
            )
        if self.PORTFOLIO_RESULT_REQUIRED_MARKER in metadata.data_manifest or (
            self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in metadata.data_manifest
        ):
            raise ResearchRunIntegrityError(
                "portfolio result manifest reserved key 不可由呼叫端預先提供"
            )
        if not result.equity_curve.reset_index(drop=True).equals(
            equity.reset_index(drop=True)
        ) or not result.trades.reset_index(drop=True).equals(
            trades.reset_index(drop=True)
        ):
            raise ResearchRunIntegrityError(
                "portfolio result DTO equity/trades 與 Registry Parquet inputs 不一致"
            )
        self._portfolio_parent_id(result)
        manifest = dict(metadata.data_manifest)
        manifest[self.PORTFOLIO_RESULT_REQUIRED_MARKER] = True
        marked = replace(metadata, data_manifest=manifest)
        # 這裡先綁定 opt-in marker。sidecar descriptor 與 Parquet digest
        # 在 raw files 落地後才可計算，屆時再由 B1 finalize command 重算。
        return replace(
            marked,
            payload_hash=self._recommendation_portfolio_payload_hash(marked),
        )

    @staticmethod
    def _validate_portfolio_lineage_status(
        metadata: ResearchRunMetadataDTO,
        *,
        portfolio_parent_id: str,
        has_lineage_sidecar: bool,
    ) -> None:
        """保存 marked DTO 前要求 lineage availability 有明確且一致的表示。"""

        manifest = metadata.data_manifest
        if type(manifest) is not dict:
            raise ResearchRunIntegrityError(
                "portfolio result data_manifest 必須是 object"
            )
        status = manifest.get("replay_lineage_status")
        if has_lineage_sidecar:
            if "replay_lineage_status" in manifest:
                raise ResearchRunIntegrityError(
                    "有 replay lineage sidecar 時不可同時提供 replay_lineage_status"
                )
            return

        if (
            type(status) is not dict
            or set(status)
            != {"schema_version", "status", "parent_result_id", "reason"}
            or type(status.get("schema_version")) is not int
            or status.get("schema_version") != 1
            or status.get("status") != "unavailable"
            or status.get("parent_result_id") != portfolio_parent_id
            or status.get("reason") != "canonical_child_unavailable"
        ):
            raise ResearchRunIntegrityError(
                "沒有 replay lineage sidecar 時必須明示 parent-bound unavailable 狀態"
            )

    def _encode_portfolio_result(
        self,
        result: RecommendationPortfolioBacktestResultDTO,
        *,
        registry_run_id: str,
        portfolio_parent_id: str,
        equity_parquet_sha256: str,
        trades_parquet_sha256: str,
    ) -> RecommendationPortfolioResultArtifactV1:
        try:
            return encode_portfolio_result_artifact(
                result,
                registry_run_id=registry_run_id,
                portfolio_parent_id=portfolio_parent_id,
                equity_parquet_sha256=equity_parquet_sha256,
                trades_parquet_sha256=trades_parquet_sha256,
            )
        except (PortfolioResultArtifactCodecError, TypeError, ValueError) as exc:
            raise ResearchRunIntegrityError(
                "portfolio result sidecar contract 無效"
            ) from exc

    def _metadata_with_portfolio_descriptor(
        self,
        metadata: ResearchRunMetadataDTO,
        artifact: RecommendationPortfolioResultArtifactV1,
        paths: dict[str, Path],
    ) -> ResearchRunMetadataDTO:
        if metadata.run_type != "recommendation_portfolio":
            raise ResearchRunIntegrityError("portfolio result metadata run_type 無效")
        if metadata.data_manifest.get(self.PORTFOLIO_RESULT_REQUIRED_MARKER) is not True:
            raise ResearchRunIntegrityError("portfolio result marker 遺失")
        if self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in metadata.data_manifest:
            raise ResearchRunIntegrityError("portfolio result descriptor 不可覆寫")
        descriptor = {
            "schema_version": artifact.schema_version,
            "schema_revision": artifact.schema_revision,
            "registry_run_id": artifact.registry_run_id,
            "portfolio_parent_id": artifact.portfolio_parent_id,
            "relative_path": paths["portfolio_result_final"].name,
            "raw_payload_sha256": artifact.raw_payload_sha256,
            "payload_hash": artifact.payload_hash,
            "equity_parquet_sha256": artifact.equity_parquet_sha256,
            "trades_parquet_sha256": artifact.trades_parquet_sha256,
        }
        manifest = dict(metadata.data_manifest)
        manifest[self.PORTFOLIO_RESULT_DESCRIPTOR_KEY] = descriptor
        finalized = replace(metadata, data_manifest=manifest)
        finalized = replace(
            finalized,
            payload_hash=self._recommendation_portfolio_payload_hash(finalized),
        )
        self._validate_portfolio_result_descriptor(finalized, paths)
        return finalized

    def _validate_portfolio_result_descriptor(
        self,
        metadata: ResearchRunMetadataDTO,
        paths: dict[str, Path],
    ) -> dict[str, Any]:
        descriptor = metadata.data_manifest.get(self.PORTFOLIO_RESULT_DESCRIPTOR_KEY)
        if (
            metadata.run_type != "recommendation_portfolio"
            or metadata.data_manifest.get(self.PORTFOLIO_RESULT_REQUIRED_MARKER) is not True
            or type(descriptor) is not dict
            or set(descriptor) != self._PORTFOLIO_RESULT_DESCRIPTOR_KEYS
        ):
            raise ResearchRunIntegrityError(
                "portfolio result manifest marker/descriptor 無效"
            )
        if (
            descriptor.get("schema_version")
            != ResearchRunRepository.PORTFOLIO_RESULT_SCHEMA_VERSION
            or type(descriptor.get("schema_revision")) is not int
            or descriptor.get("schema_revision")
            != ResearchRunRepository.PORTFOLIO_RESULT_SCHEMA_REVISION
        ):
            raise ResearchRunIntegrityError(
                "portfolio result descriptor schema 不支援"
            )
        if (
            descriptor.get("registry_run_id") != metadata.run_id
            or type(descriptor.get("portfolio_parent_id")) is not str
            or not descriptor["portfolio_parent_id"].strip()
            or descriptor["portfolio_parent_id"] == metadata.run_id
        ):
            raise ResearchRunIntegrityError(
                "portfolio result descriptor identity 無效"
            )
        if descriptor.get("relative_path") != paths["portfolio_result_final"].name:
            raise ResearchRunIntegrityError(
                "portfolio result descriptor path 不符合 Registry 路徑"
            )
        for key in (
            "raw_payload_sha256",
            "payload_hash",
            "equity_parquet_sha256",
            "trades_parquet_sha256",
        ):
            value = descriptor.get(key)
            if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                raise ResearchRunIntegrityError(
                    f"portfolio result descriptor {key} 格式無效"
                )
        if (
            descriptor["equity_parquet_sha256"] != metadata.equity_parquet_hash
            or descriptor["trades_parquet_sha256"] != metadata.trades_parquet_hash
        ):
            raise ResearchRunIntegrityError(
                "portfolio result Parquet hash 與 metadata 不一致"
            )
        parquet_root = self.parquet_dir.resolve()
        for field, expected_path in (
            ("equity_path", paths["equity_final"]),
            ("trades_path", paths["trades_final"]),
        ):
            try:
                actual = Path(getattr(metadata, field)).resolve(strict=False)
                expected = expected_path.resolve(strict=False)
                actual.relative_to(parquet_root)
            except (OSError, ValueError) as exc:
                raise ResearchRunIntegrityError(
                    f"portfolio result {field} 超出設定 Parquet root"
                ) from exc
            if actual != expected:
                raise ResearchRunIntegrityError(
                    f"portfolio result {field} 不符合 Registry final path"
                )
        if self._recommendation_portfolio_payload_hash(metadata) != metadata.payload_hash:
            raise ResearchRunIntegrityError(
                "Research Run payload_hash 未綁定 portfolio result descriptor"
            )
        return descriptor

    def _read_portfolio_result_file(
        self,
        metadata: ResearchRunMetadataDTO,
        path: Path,
        *,
        expected_path: Path,
    ) -> RecommendationPortfolioResultArtifactV1:
        if path != expected_path:
            raise ResearchRunIntegrityError(
                "portfolio result sidecar path 不符合預期"
            )
        if self._is_symlink_or_reparse_point(path):
            raise ResearchRunIntegrityError(
                "portfolio result sidecar 不可為 symlink 或 reparse point"
            )
        paths = self._paths_for(metadata.run_id)
        descriptor = self._validate_portfolio_result_descriptor(metadata, paths)
        try:
            raw_payload = path.read_bytes()
            artifact = decode_portfolio_result_artifact(raw_payload)
        except (OSError, PortfolioResultArtifactCodecError, TypeError, ValueError) as exc:
            raise ResearchRunIntegrityError(
                "portfolio result sidecar bytes 無法驗證"
            ) from exc
        if (
            artifact.registry_run_id != descriptor["registry_run_id"]
            or artifact.portfolio_parent_id != descriptor["portfolio_parent_id"]
            or artifact.raw_payload_sha256 != descriptor["raw_payload_sha256"]
            or artifact.payload_hash != descriptor["payload_hash"]
            or artifact.equity_parquet_sha256 != descriptor["equity_parquet_sha256"]
            or artifact.trades_parquet_sha256 != descriptor["trades_parquet_sha256"]
        ):
            raise ResearchRunIntegrityError(
                "portfolio result sidecar bytes 與 Registry descriptor 不一致"
            )
        return artifact

    def _validate_portfolio_result_file(
        self,
        metadata: ResearchRunMetadataDTO,
        path: Path,
        *,
        expected_path: Path,
    ) -> RecommendationPortfolioResultArtifactV1:
        return self._read_portfolio_result_file(
            metadata, path, expected_path=expected_path
        )

    def _return_existing_portfolio_result(
        self,
        *,
        existing_raw: dict[str, Any],
        existing: ResearchRunMetadataDTO | None,
        base_metadata: ResearchRunMetadataDTO,
        result: RecommendationPortfolioBacktestResultDTO,
        equity: pd.DataFrame,
        trades: pd.DataFrame,
        replay_lineage_bytes: bytes | None,
    ) -> ResearchRunMetadataDTO:
        run_id = base_metadata.run_id
        if existing is None or existing_raw["storage_state"] != "committed":
            raise ResearchRunIntegrityError(
                f"portfolio result run 尚未完整提交，不可接管: {run_id}"
            )
        if existing_raw["integrity_status"] != "valid":
            raise ResearchRunIntegrityError(
                f"portfolio result run integrity status 無效: {run_id}"
            )
        saved = self.load_run_data(run_id)
        if saved.portfolio_result_artifact is None:
            raise ResearchRunConflictError(
                "既有 run 未宣告完整 portfolio result sidecar"
            )
        paths = self._paths_for(run_id)
        artifact = self._encode_portfolio_result(
            result,
            registry_run_id=run_id,
            portfolio_parent_id=self._portfolio_parent_id(result),
            equity_parquet_sha256=existing.equity_parquet_hash,
            trades_parquet_sha256=existing.trades_parquet_hash,
        )
        expected_metadata = replace(
            base_metadata,
            equity_path=existing.equity_path,
            equity_parquet_hash=existing.equity_parquet_hash,
            trades_path=existing.trades_path,
            trades_parquet_hash=existing.trades_parquet_hash,
        )
        expected_metadata = self._metadata_with_portfolio_descriptor(
            expected_metadata, artifact, paths
        )
        if (
            self._immutable_metadata(saved.metadata)
            != self._immutable_metadata(expected_metadata)
            or not saved.equity.equals(equity.reset_index(drop=True))
            or not saved.trades.equals(trades.reset_index(drop=True))
            or saved.portfolio_result_artifact.raw_payload != artifact.raw_payload
            or (
                saved.replay_lineage.raw_payload
                if saved.replay_lineage is not None
                else None
            )
            != replay_lineage_bytes
        ):
            raise ResearchRunConflictError(
                "相同 run_id 的 portfolio result content 不同"
            )
        return saved.metadata

    @staticmethod
    def _hash_bytes(payload: bytes) -> str:
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def _read_verified_bytes(self, path: Path, expected_hash: str) -> bytes:
        if self._is_symlink_or_reparse_point(path):
            raise ResearchRunIntegrityError(
                f"payload 檔案不可為 symlink 或 reparse point: {path}"
            )
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ResearchRunIntegrityError(f"payload 檔案不存在或無法讀取: {path}") from exc
        if self._hash_bytes(payload) != expected_hash:
            raise ResearchRunIntegrityError(f"payload hash 不一致: {path}")
        return payload

    @staticmethod
    def _parse_portfolio_parquet_bytes(
        equity_bytes: bytes, trades_bytes: bytes
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """解析已驗 hash 的同次 Parquet bytes，避免再從路徑讀第二次。"""

        try:
            equity = pd.read_parquet(BytesIO(equity_bytes))
            trades = pd.read_parquet(BytesIO(trades_bytes))
        except Exception as exc:
            raise ResearchRunIntegrityError(
                "portfolio Parquet bytes 無法解析"
            ) from exc
        return equity, trades

    def _write_parquet_temp_create_only(self, frame: pd.DataFrame, path: Path) -> None:
        buffer = BytesIO()
        frame.to_parquet(buffer, index=False)
        self._write_bytes_create_only(path, buffer.getvalue())

    @staticmethod
    def _parquet_frame_copy(frame: pd.DataFrame) -> pd.DataFrame:
        """複製表格，僅將 attrs 中有限 Decimal 轉成精確字串供 Parquet metadata 使用。"""

        copied = frame.copy(deep=True)
        normalized_attrs = normalize_research_run_json_value(copied.attrs)
        if type(normalized_attrs) is not dict:
            raise TypeError("DataFrame attrs 必須是 object")
        copied.attrs = normalized_attrs
        return copied

    def _assert_portfolio_paths_unclaimed(self, paths: dict[str, Path]) -> None:
        for key in (
            "equity_temp",
            "trades_temp",
            "equity_final",
            "trades_final",
            "portfolio_result_temp",
            "portfolio_result_final",
        ):
            path = paths[key]
            if path.exists() or self._is_symlink_or_reparse_point(path):
                raise ResearchRunConflictError(
                    f"portfolio result artifact orphan/existing bytes 已存在: {path}"
                )

    def _write_bytes_create_only(self, path: Path, payload: bytes) -> None:
        if self._is_symlink_or_reparse_point(path):
            raise ResearchRunConflictError(f"staging path 不可為 symlink: {path}")
        if path.exists():
            if path.read_bytes() != payload:
                raise ResearchRunConflictError(
                    f"既有 staging bytes 不同；拒絕覆寫: {path}"
                )
            return
        try:
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if (
                self._is_symlink_or_reparse_point(path)
                or path.read_bytes() != payload
            ):
                raise ResearchRunConflictError(
                    f"競爭建立的 staging bytes 不同；拒絕覆寫: {path}"
                )

    def _publish_bytes_create_only(
        self,
        temp_path: Path,
        final_path: Path,
        *,
        expected_hash: str,
    ) -> None:
        temp_bytes = self._read_verified_bytes(temp_path, expected_hash)
        if self._is_symlink_or_reparse_point(final_path):
            raise ResearchRunIntegrityError(
                f"final artifact 不可為 symlink 或 reparse point: {final_path}"
            )
        if final_path.exists():
            if self._read_verified_bytes(final_path, expected_hash) != temp_bytes:
                raise ResearchRunConflictError(
                    f"既有 final artifact bytes 不同；拒絕覆寫: {final_path}"
                )
        else:
            try:
                os.link(temp_path, final_path)
            except FileExistsError:
                if self._read_verified_bytes(final_path, expected_hash) != temp_bytes:
                    raise ResearchRunConflictError(
                        f"競爭發布的 final artifact bytes 不同: {final_path}"
                    )
            self._read_verified_bytes(final_path, expected_hash)
        if temp_path.exists():
            if self._is_symlink_or_reparse_point(temp_path):
                raise ResearchRunIntegrityError(
                    f"staging artifact 不可為 symlink: {temp_path}"
                )
            if temp_path.read_bytes() != temp_bytes:
                raise ResearchRunConflictError(
                    f"staging/final bytes 不同；拒絕清除: {temp_path}"
                )
            temp_path.unlink()

    def _verify_marked_parquet_temp(
        self,
        metadata: ResearchRunMetadataDTO,
        paths: dict[str, Path],
    ) -> None:
        self._validate_portfolio_result_descriptor(metadata, paths)
        self._read_verified_bytes(paths["equity_temp"], metadata.equity_parquet_hash)
        self._read_verified_bytes(paths["trades_temp"], metadata.trades_parquet_hash)

    def _verify_marked_parquet_final(
        self,
        metadata: ResearchRunMetadataDTO,
        paths: dict[str, Path],
    ) -> tuple[bytes, bytes]:
        self._validate_portfolio_result_descriptor(metadata, paths)
        equity_bytes = self._read_verified_bytes(
            paths["equity_final"], metadata.equity_parquet_hash
        )
        trades_bytes = self._read_verified_bytes(
            paths["trades_final"], metadata.trades_parquet_hash
        )
        return equity_bytes, trades_bytes

    def load_run_data(self, run_id: str) -> ResearchRunData:
        raw = self.repository.get_raw_metadata_row(run_id)
        metadata = self.repository.get_metadata(run_id)
        if raw is None or metadata is None:
            raise ResearchRunIntegrityError(f"找不到 research run: {run_id}")
        if raw["storage_state"] != "committed" or raw["integrity_status"] != "valid":
            raise ResearchRunIntegrityError(f"run 尚未通過完整性檢查: {run_id}")
        self._metadata_with_execution_contract(metadata)
        paths = self._paths_for(run_id)
        marker_present = self.PORTFOLIO_RESULT_REQUIRED_MARKER in metadata.data_manifest
        descriptor_present = self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in metadata.data_manifest
        if marker_present:
            if metadata.data_manifest.get(self.PORTFOLIO_RESULT_REQUIRED_MARKER) is not True:
                raise ResearchRunIntegrityError("portfolio result marker 必須是 true")
            self._validate_portfolio_result_descriptor(metadata, paths)
            # 對 marked run，驗 hash與解析都使用同次讀到的 bytes，避免驗證後路徑
            # 被替換造成 TOCTOU。Stage C 可直接接收這個已驗 sidecar envelope。
            equity_bytes, trades_bytes = self._verify_marked_parquet_final(
                metadata, paths
            )
            artifact = self._read_portfolio_result_file(
                metadata,
                paths["portfolio_result_final"],
                expected_path=paths["portfolio_result_final"],
            )
            equity, trades = self._parse_portfolio_parquet_bytes(
                equity_bytes, trades_bytes
            )
        else:
            if descriptor_present or (
                paths["portfolio_result_temp"].exists()
                or paths["portfolio_result_final"].exists()
                or self._is_symlink_or_reparse_point(paths["portfolio_result_temp"])
                or self._is_symlink_or_reparse_point(paths["portfolio_result_final"])
            ):
                raise ResearchRunIntegrityError(
                    "未宣告 portfolio result marker 的 run 出現 sidecar 或 orphan bytes"
                )
            self._verify_hash(Path(metadata.equity_path), metadata.equity_parquet_hash)
            self._verify_hash(Path(metadata.trades_path), metadata.trades_parquet_hash)
            equity = pd.read_parquet(metadata.equity_path)
            trades = pd.read_parquet(metadata.trades_path)
            artifact = None
        replay_lineage = self._load_replay_lineage(metadata)
        if (
            artifact is not None
            and replay_lineage is not None
            and artifact.portfolio_parent_id
            != replay_lineage.sidecar.parent_result_id
        ):
            raise ResearchRunIntegrityError(
                "portfolio result 與 replay lineage parent identity 不一致"
            )
        return ResearchRunData(
            metadata=metadata,
            equity=equity,
            trades=trades,
            replay_lineage=replay_lineage,
            portfolio_result_artifact=artifact,
        )

    def list_runs(self, *, include_archived: bool = False) -> list[ResearchRunMetadataDTO]:
        runs = self.repository.list_metadata(include_archived=include_archived)
        return [
            run for run in runs
            if (row := self.repository.get_raw_metadata_row(run.run_id))
            and row["storage_state"] == "committed" and row["integrity_status"] == "valid"
        ]

    @staticmethod
    def _immutable_metadata(metadata: ResearchRunMetadataDTO) -> dict[str, Any]:
        value = normalize_research_run_json_value(asdict(metadata))
        for field in ("equity_path", "equity_parquet_hash", "trades_path", "trades_parquet_hash",
                      "is_archived", "promoted_version_id", "promotion_reconciliation_status"):
            value.pop(field, None)
        return value

    @staticmethod
    def _metadata_with_execution_contract(metadata: ResearchRunMetadataDTO) -> ResearchRunMetadataDTO:
        contract = metadata.execution_contract
        if contract not in {"next-session-open.v2", "legacy-same-day-close.v1", "unversioned"}:
            raise ResearchRunIntegrityError(f"不支援的執行契約: {contract}")
        declared = metadata.data_manifest.get("execution_contract")
        if declared and metadata.execution_price in {"next-session-open.v2", "legacy-same-day-close.v1"}:
            if declared != metadata.execution_price:
                raise ResearchRunIntegrityError("metadata 與 manifest 執行契約不一致")
        if contract == "unversioned":
            return metadata
        return replace(metadata, execution_price=contract,
                       data_manifest={**metadata.data_manifest, "execution_contract": contract})

    def archive_run(self, run_id: str) -> None:
        metadata = self.repository.get_metadata(run_id)
        if metadata is None:
            raise ResearchRunIntegrityError(f"找不到 research run: {run_id}")
        if metadata.promoted_version_id:
            raise PromotedResearchRunArchiveError(
                f"已升級策略版本的 run 不可封存: {run_id}"
            )
        self.repository.archive_run(run_id)

    def reconcile_incomplete_saves(self) -> None:
        for row in self.repository.list_uncommitted_rows():
            run_id = row["run_id"]
            metadata = self.repository.get_metadata(run_id)
            if metadata is None:
                continue
            marked_portfolio = (
                self.PORTFOLIO_RESULT_REQUIRED_MARKER in metadata.data_manifest
                or self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in metadata.data_manifest
            )
            if marked_portfolio:
                state = str(row["storage_state"])
                integrity = str(row["integrity_status"])
                payload_hash = str(row["payload_hash"])
                if state == "staging":
                    try:
                        self.repository.mark_portfolio_result_failed(
                            run_id,
                            expected_payload_hash=payload_hash,
                            expected_data_manifest=metadata.data_manifest,
                            expected_storage_state=state,
                            expected_integrity_status=integrity,
                        )
                    except ResearchRunConflictError:
                        # 另一個 owner 已完成狀態轉移；不得以舊 snapshot 覆寫。
                        pass
                    continue
                if self._finish_portfolio_files_ready_row(row, metadata):
                    try:
                        self.repository.mark_portfolio_result_committed(
                            run_id,
                            expected_payload_hash=payload_hash,
                            expected_data_manifest=metadata.data_manifest,
                        )
                    except ResearchRunConflictError:
                        # 另一個 reconciler/owner 已先完成；CAS 保護 committed row。
                        pass
                else:
                    try:
                        self.repository.mark_portfolio_result_failed(
                            run_id,
                            expected_payload_hash=payload_hash,
                            expected_data_manifest=metadata.data_manifest,
                            expected_storage_state=state,
                            expected_integrity_status=integrity,
                        )
                    except ResearchRunConflictError:
                        pass
                continue

            if row["storage_state"] == "staging":
                self.repository.update_storage_fields(
                    run_id,
                    storage_state="failed",
                    integrity_status="failed",
                )
                continue

            if not self._finish_files_ready_row(row):
                self.repository.update_storage_fields(
                    run_id,
                    storage_state="failed",
                    integrity_status="failed",
                )

    def _finish_portfolio_files_ready_row(
        self,
        row: dict[str, Any],
        metadata: ResearchRunMetadataDTO,
    ) -> bool:
        """只驗證並發布完整 marked artifact；狀態 commit 由呼叫端 CAS。"""

        run_id = str(row["run_id"])
        paths = self._paths_for(run_id)
        try:
            self._validate_portfolio_result_descriptor(metadata, paths)
            parquet_pairs = (
                (
                    paths["equity_temp"],
                    paths["equity_final"],
                    metadata.equity_parquet_hash,
                ),
                (
                    paths["trades_temp"],
                    paths["trades_final"],
                    metadata.trades_parquet_hash,
                ),
            )
            selected_payloads: list[tuple[Path, Path, str, bytes]] = []
            for temp_path, final_path, expected_hash in parquet_pairs:
                final_bytes = (
                    self._read_verified_bytes(final_path, expected_hash)
                    if final_path.exists()
                    else None
                )
                temp_bytes = (
                    self._read_verified_bytes(temp_path, expected_hash)
                    if temp_path.exists()
                    else None
                )
                if final_bytes is None and temp_bytes is None:
                    return False
                if final_bytes is not None and temp_bytes is not None and final_bytes != temp_bytes:
                    return False
                selected_payloads.append(
                    (temp_path, final_path, expected_hash, final_bytes or temp_bytes or b"")
                )

            self._parse_portfolio_parquet_bytes(
                selected_payloads[0][3], selected_payloads[1][3]
            )

            sidecar_temp = paths["portfolio_result_temp"]
            sidecar_final = paths["portfolio_result_final"]
            sidecar_artifacts: list[RecommendationPortfolioResultArtifactV1] = []
            if sidecar_temp.exists():
                sidecar_artifacts.append(
                    self._read_portfolio_result_file(
                        metadata, sidecar_temp, expected_path=sidecar_temp
                    )
                )
            if sidecar_final.exists():
                sidecar_artifacts.append(
                    self._read_portfolio_result_file(
                        metadata, sidecar_final, expected_path=sidecar_final
                    )
                )
            if not sidecar_artifacts or any(
                item.raw_payload != sidecar_artifacts[0].raw_payload
                for item in sidecar_artifacts[1:]
            ):
                return False
            sidecar_artifact = sidecar_artifacts[0]

            lineage_descriptor = metadata.data_manifest.get(
                self.REPLAY_LINEAGE_MANIFEST_KEY
            )
            lineage_temp = paths["replay_lineage_temp"]
            lineage_final = paths["replay_lineage_final"]
            lineage_present = lineage_temp.exists() or lineage_final.exists()
            if lineage_descriptor is not None:
                envelopes: list[ReplayLineageReadEnvelope] = []
                if lineage_temp.exists():
                    envelopes.append(
                        self._read_replay_lineage_file(metadata, lineage_temp)
                    )
                if lineage_final.exists():
                    envelopes.append(
                        self._read_replay_lineage_file(metadata, lineage_final)
                    )
                if not envelopes or any(
                    item.raw_payload != envelopes[0].raw_payload
                    for item in envelopes[1:]
                ):
                    return False
                if (
                    envelopes[0].sidecar.parent_result_id
                    != sidecar_artifact.portfolio_parent_id
                ):
                    return False
            elif lineage_present:
                # descriptor 不存在時不得把 orphan lineage 一併提交。
                return False

            # 先完成所有來源 bytes/descriptor 驗證，再開始 create-only publish。
            for temp_path, final_path, expected_hash, selected_bytes in selected_payloads:
                if not final_path.exists():
                    if not temp_path.exists():
                        return False
                    self._publish_bytes_create_only(
                        temp_path, final_path, expected_hash=expected_hash
                    )
                elif temp_path.exists():
                    self._publish_bytes_create_only(
                        temp_path, final_path, expected_hash=expected_hash
                    )
                if self._read_verified_bytes(final_path, expected_hash) != selected_bytes:
                    return False

            if not sidecar_final.exists():
                if not sidecar_temp.exists():
                    return False
                self._publish_bytes_create_only(
                    sidecar_temp,
                    sidecar_final,
                    expected_hash=sidecar_artifact.raw_payload_sha256,
                )
            elif sidecar_temp.exists():
                self._publish_bytes_create_only(
                    sidecar_temp,
                    sidecar_final,
                    expected_hash=sidecar_artifact.raw_payload_sha256,
                )
            final_artifact = self._read_portfolio_result_file(
                metadata, sidecar_final, expected_path=sidecar_final
            )
            if final_artifact.raw_payload != sidecar_artifact.raw_payload:
                return False

            if lineage_descriptor is not None:
                if not lineage_final.exists():
                    if not lineage_temp.exists():
                        return False
                    self._publish_replay_lineage(
                        metadata, lineage_temp, lineage_final
                    )
                elif lineage_temp.exists():
                    self._remove_identical_replay_lineage_temp(
                        metadata, lineage_temp, lineage_final
                    )
                self._read_replay_lineage_file(metadata, lineage_final)
            return True
        except (
            OSError,
            ResearchRunConflictError,
            ResearchRunIntegrityError,
            ResearchRunRepositoryError,
        ):
            return False

    def _finish_files_ready_row(self, row: dict[str, Any]) -> bool:
        run_id = str(row["run_id"])
        paths = self._paths_for(run_id)
        expected = [
            (
                paths["equity_temp"],
                Path(row["equity_path"]),
                row["equity_parquet_hash"],
            ),
            (
                paths["trades_temp"],
                Path(row["trades_path"]),
                row["trades_parquet_hash"],
            ),
        ]

        try:
            for temp_path, final_path, _expected_hash in expected:
                if not final_path.exists():
                    if temp_path.exists():
                        os.replace(temp_path, final_path)
                    else:
                        return False
            for _temp_path, final_path, expected_hash in expected:
                self._verify_hash(final_path, str(expected_hash))
            metadata = self.repository.get_metadata(run_id)
            if metadata is None:
                return False
            has_lineage_descriptor = (
                self.REPLAY_LINEAGE_MANIFEST_KEY in metadata.data_manifest
            )
            if has_lineage_descriptor:
                if paths["replay_lineage_final"].exists():
                    self._read_replay_lineage_file(
                        metadata, paths["replay_lineage_final"]
                    )
                    self._remove_identical_replay_lineage_temp(
                        metadata,
                        paths["replay_lineage_temp"],
                        paths["replay_lineage_final"],
                    )
                elif paths["replay_lineage_temp"].exists():
                    self._publish_replay_lineage(
                        metadata,
                        paths["replay_lineage_temp"],
                        paths["replay_lineage_final"],
                    )
                else:
                    return False
            elif (
                paths["replay_lineage_temp"].exists()
                or paths["replay_lineage_final"].exists()
            ):
                # manifest 沒有 descriptor 時，不接收無主 sidecar。
                return False
        except (OSError, ResearchRunConflictError, ResearchRunIntegrityError):
            return False

        self.repository.update_storage_fields(
            run_id,
            storage_state="committed",
            integrity_status="valid",
        )
        return True

    def _paths_for(self, run_id: str) -> dict[str, Path]:
        file_stem = self._safe_file_stem(run_id)
        return {
            "equity_temp": self.staging_dir / f"{file_stem}_equity.tmp.parquet",
            "trades_temp": self.staging_dir / f"{file_stem}_trades.tmp.parquet",
            "equity_final": self.parquet_dir / f"{file_stem}_equity.parquet",
            "trades_final": self.parquet_dir / f"{file_stem}_trades.parquet",
            "portfolio_result_temp": self.staging_dir / f"{file_stem}_portfolio_result.tmp.json",
            "portfolio_result_final": self.parquet_dir / f"{file_stem}_portfolio_result.json",
            "replay_lineage_temp": self.staging_dir / f"{file_stem}_replay_lineage.tmp.json",
            "replay_lineage_final": self.parquet_dir / f"{file_stem}_replay_lineage.json",
        }

    def _metadata_with_replay_lineage(
        self,
        metadata: ResearchRunMetadataDTO,
        envelope: ReplayLineageReadEnvelope,
        paths: dict[str, Path],
    ) -> ResearchRunMetadataDTO:
        if metadata.run_type != "recommendation_portfolio":
            raise ResearchRunIntegrityError(
                "replay lineage sidecar 只可附加到 recommendation_portfolio run"
            )
        if envelope.sidecar.parent_result_id == metadata.run_id:
            raise ResearchRunIntegrityError(
                "replay parent result_id 必須與 Research Run Registry run_id 分離"
            )
        descriptor = self._replay_lineage_descriptor(envelope, paths)
        if (
            self.REPLAY_LINEAGE_MANIFEST_KEY in metadata.data_manifest
            and metadata.data_manifest[self.REPLAY_LINEAGE_MANIFEST_KEY] != descriptor
        ):
            raise ResearchRunIntegrityError(
                "metadata replay lineage descriptor 與 sidecar 不一致"
            )
        manifest = dict(metadata.data_manifest)
        manifest[self.REPLAY_LINEAGE_MANIFEST_KEY] = descriptor
        bound_metadata = replace(metadata, data_manifest=manifest)
        payload_hash = self._recommendation_portfolio_payload_hash(bound_metadata)
        return replace(bound_metadata, payload_hash=payload_hash)

    def _replay_lineage_descriptor(
        self,
        envelope: ReplayLineageReadEnvelope,
        paths: dict[str, Path],
    ) -> dict[str, Any]:
        return {
            "schema_version": envelope.schema_version,
            "schema_revision": envelope.schema_revision,
            "parent_result_id": envelope.sidecar.parent_result_id,
            "relative_path": paths["replay_lineage_final"].name,
            "raw_payload_sha256": envelope.raw_payload_sha256,
            "payload_hash": envelope.payload_hash,
            "child_count": len(envelope.sidecar.children),
        }

    def _recommendation_portfolio_payload_hash(
        self, metadata: ResearchRunMetadataDTO
    ) -> str:
        if metadata.run_type != "recommendation_portfolio":
            raise ResearchRunIntegrityError(
                "sidecar payload hash 只支援 recommendation_portfolio metadata"
            )
        config = metadata.original_input.get("config")
        if not isinstance(config, dict):
            raise ResearchRunIntegrityError(
                "recommendation_portfolio metadata 缺少 original_input.config"
            )
        payload = {
            "run_type": "recommendation_portfolio",
            "config": config,
            "run_params": metadata.normalized_params,
            "metrics": metadata.metrics,
            "data_manifest": metadata.data_manifest,
        }
        try:
            canonical = canonical_json(self._research_json_safe(payload)).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ResearchRunIntegrityError(
                "recommendation_portfolio metadata 無法計算 canonical payload hash"
            ) from exc
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    @classmethod
    def _research_json_safe(cls, value: Any) -> Any:
        """比照 portfolio metadata builder 的 JSON 安全 payload 規則。"""
        if isinstance(value, pd.DataFrame):
            return value.to_dict(orient="records")
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {str(key): cls._research_json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._research_json_safe(item) for item in value]
        if hasattr(value, "value") and value.__class__.__name__.endswith("Status"):
            return value.value
        return value

    def _load_replay_lineage(
        self, metadata: ResearchRunMetadataDTO
    ) -> ReplayLineageReadEnvelope | None:
        if self.REPLAY_LINEAGE_MANIFEST_KEY not in metadata.data_manifest:
            return None
        paths = self._paths_for(metadata.run_id)
        return self._read_replay_lineage_file(metadata, paths["replay_lineage_final"])

    def _validate_replay_lineage_descriptor(
        self,
        metadata: ResearchRunMetadataDTO,
        paths: dict[str, Path],
    ) -> dict[str, Any]:
        descriptor = metadata.data_manifest.get(self.REPLAY_LINEAGE_MANIFEST_KEY)
        if type(descriptor) is not dict or set(descriptor) != self._REPLAY_LINEAGE_DESCRIPTOR_KEYS:
            raise ResearchRunIntegrityError("replay lineage manifest descriptor 欄位無效")
        if metadata.run_type != "recommendation_portfolio":
            raise ResearchRunIntegrityError("非 portfolio run 不得附帶 replay lineage")
        if descriptor.get("schema_version") != REPLAY_LINEAGE_SCHEMA_VERSION:
            raise ResearchRunIntegrityError("replay lineage manifest schema_version 不支援")
        if (
            type(descriptor.get("schema_revision")) is not int
            or descriptor["schema_revision"] != REPLAY_LINEAGE_SCHEMA_REVISION
        ):
            raise ResearchRunIntegrityError("replay lineage manifest schema_revision 不支援")
        parent_result_id = descriptor.get("parent_result_id")
        if (
            type(parent_result_id) is not str
            or not parent_result_id.strip()
            or parent_result_id == metadata.run_id
        ):
            raise ResearchRunIntegrityError("replay lineage manifest parent identity 無效")
        if type(descriptor.get("child_count")) is not int or descriptor["child_count"] < 0:
            raise ResearchRunIntegrityError("replay lineage manifest child_count 無效")
        if descriptor.get("relative_path") != paths["replay_lineage_final"].name:
            raise ResearchRunIntegrityError("replay lineage manifest path 不符合 Registry 路徑")
        for hash_field in ("raw_payload_sha256", "payload_hash"):
            value = descriptor.get(hash_field)
            if (
                type(value) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            ):
                raise ResearchRunIntegrityError(
                    f"replay lineage manifest {hash_field} 無效"
                )
        if self._recommendation_portfolio_payload_hash(metadata) != metadata.payload_hash:
            raise ResearchRunIntegrityError(
                "Research Run payload_hash 未綁定 replay lineage descriptor"
            )
        return descriptor

    def _read_replay_lineage_file(
        self,
        metadata: ResearchRunMetadataDTO,
        path: Path,
    ) -> ReplayLineageReadEnvelope:
        paths = self._paths_for(metadata.run_id)
        descriptor = self._validate_replay_lineage_descriptor(metadata, paths)
        if path != paths["replay_lineage_final"] and path != paths["replay_lineage_temp"]:
            raise ResearchRunIntegrityError("replay lineage file path 不符合預期")
        if self._is_symlink_or_reparse_point(path):
            raise ResearchRunIntegrityError("replay lineage file 不可為 symlink 或 reparse point")
        try:
            raw_payload = path.read_bytes()
            envelope = decode_replay_lineage_envelope(raw_payload)
        except (OSError, ReplayLineageCodecError, TypeError, ValueError) as exc:
            raise ResearchRunIntegrityError("replay lineage sidecar 無法驗證") from exc
        if (
            envelope.schema_version != descriptor["schema_version"]
            or envelope.schema_revision != descriptor["schema_revision"]
            or envelope.sidecar.parent_result_id != descriptor["parent_result_id"]
            or len(envelope.sidecar.children) != descriptor["child_count"]
            or envelope.raw_payload_sha256 != descriptor["raw_payload_sha256"]
            or envelope.payload_hash != descriptor["payload_hash"]
        ):
            raise ResearchRunIntegrityError(
                "replay lineage sidecar 與 manifest descriptor 不一致"
            )
        return envelope

    def _write_replay_lineage_temp(self, path: Path, raw_payload: bytes) -> None:
        if self._is_symlink_or_reparse_point(path):
            raise ResearchRunConflictError("replay lineage staging path 不可為 symlink")
        if path.exists():
            if path.read_bytes() != raw_payload:
                raise ResearchRunConflictError(
                    "既有 replay lineage staging bytes 不同；拒絕覆寫"
                )
            return
        try:
            with path.open("xb") as handle:
                handle.write(raw_payload)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if self._is_symlink_or_reparse_point(path) or path.read_bytes() != raw_payload:
                raise ResearchRunConflictError(
                    "競爭建立的 replay lineage staging bytes 不同；拒絕覆寫"
                )

    def _publish_replay_lineage(
        self,
        metadata: ResearchRunMetadataDTO,
        temp_path: Path,
        final_path: Path,
    ) -> None:
        self._read_replay_lineage_file(metadata, temp_path)
        if self._is_symlink_or_reparse_point(final_path):
            raise ResearchRunIntegrityError(
                "replay lineage final path 不可為 symlink 或 reparse point"
            )
        if final_path.exists():
            self._read_replay_lineage_file(metadata, final_path)
            self._remove_identical_replay_lineage_temp(metadata, temp_path, final_path)
            return
        try:
            # 同一檔案系統的硬連結提供原子且僅建立發布；不支援時採 fail closed。
            os.link(temp_path, final_path)
        except FileExistsError:
            # 另一個 reconciler 可能已發布相同 immutable bytes。
            self._read_replay_lineage_file(metadata, final_path)
        except OSError:
            # 不退回串流寫入，避免留下部分最終 bytes。
            raise
        self._read_replay_lineage_file(metadata, final_path)
        self._remove_identical_replay_lineage_temp(metadata, temp_path, final_path)

    def _remove_identical_replay_lineage_temp(
        self,
        metadata: ResearchRunMetadataDTO,
        temp_path: Path,
        final_path: Path,
    ) -> None:
        final_envelope = self._read_replay_lineage_file(metadata, final_path)
        if temp_path.exists():
            temp_envelope = self._read_replay_lineage_file(metadata, temp_path)
            if temp_envelope.raw_payload != final_envelope.raw_payload:
                raise ResearchRunConflictError(
                    "replay lineage staging/final bytes 不同；拒絕清除或覆寫"
            )
            temp_path.unlink()

    @staticmethod
    def _is_symlink_or_reparse_point(path: Path) -> bool:
        try:
            path_stat = path.lstat()
        except FileNotFoundError:
            return False
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return stat.S_ISLNK(path_stat.st_mode) or bool(
            getattr(path_stat, "st_file_attributes", 0) & reparse_flag
        )

    def _safe_file_stem(self, run_id: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("._")
        suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
        return f"{sanitized}_{suffix}" if sanitized else suffix

    def _metadata_with_factor_manifest(
        self,
        metadata: ResearchRunMetadataDTO,
        *,
        factor_records: list[FactorRecord] | None,
        factor_decision_date: date | None,
        factor_snapshot: dict[str, Any] | None,
        factor_contributions: dict[str, Any] | None,
    ) -> ResearchRunMetadataDTO:
        if factor_records is None and factor_snapshot is None and factor_contributions is None:
            return metadata

        factor_service = FactorService()
        snapshot = dict(factor_snapshot) if factor_snapshot is not None else None
        if factor_records is not None:
            if factor_decision_date is None:
                raise ValueError("factor_decision_date is required when factor_records are provided")
            snapshot = factor_service.build_snapshot(
                factor_records,
                decision_date=factor_decision_date,
            )
        contributions = (
            dict(factor_contributions)
            if factor_contributions is not None
            else factor_service.build_contributions(snapshot or {})
        )
        data_manifest = dict(metadata.data_manifest)
        if snapshot is not None:
            data_manifest["factor_snapshot"] = snapshot
        data_manifest["factor_contributions"] = contributions
        return replace(metadata, data_manifest=data_manifest)

    def _verify_hash(self, path: Path, expected_hash: str) -> None:
        if not path.exists():
            raise ResearchRunIntegrityError(f"payload 檔案不存在: {path}")
        actual = self._sha256_file(path)
        if actual != expected_hash:
            raise ResearchRunIntegrityError(f"payload hash 不一致: {path}")

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    def _fail_if_requested(self, fail_at: str | None, point: str) -> None:
        if fail_at == point:
            raise InjectedResearchRunFailure(point)
