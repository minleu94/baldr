"""Fail-closed consumer for producer-owned shadow model artifacts.

This module validates the B-owned manifest and load contract before invoking
joblib.  It intentionally does not build features or run model inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any, Callable, Mapping, Protocol

import joblib

from ml_module.model_artifact_manifest import FeatureSchema, ModelArtifactManifest


_DEFAULT_JOBLIB_LOAD = joblib.load
_SAME_BYTES_SCHEMA_VERSION = "shadow-model-artifact-same-bytes.v1"
_MANIFEST_SAME_BYTES_SCHEMA_VERSION = "shadow-model-artifact-manifest-same-bytes.v1"
_SAME_BYTES_SPOOL_MEMORY_LIMIT = 8 * 1024 * 1024


class _VerifiedArtifactBuffer(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...

    def tell(self) -> int: ...


@dataclass(frozen=True)
class ArtifactCompatibilityExpectation:
    expected_model_family: str
    expected_feature_registry_hash: str
    expected_label_registry_hash: str
    expected_feature_schema: FeatureSchema
    installed_library_versions: Mapping[str, str]


@dataclass(frozen=True)
class ShadowModelArtifactLoadResult:
    status: str
    manifest: ModelArtifactManifest | None
    model: Any | None
    blockers: tuple[str, ...]
    formal_rule_unchanged: bool = True
    production_action_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.formal_rule_unchanged or self.production_action_allowed:
            raise ValueError("artifact load result must preserve the formal rule path")
        if self.status == "shadow_model_ready":
            if self.manifest is None or self.model is None or self.blockers:
                raise ValueError("ready artifact result requires manifest and model")
        elif self.status == "rule_only_fallback":
            if self.model is not None or not self.blockers:
                raise ValueError("fallback artifact result requires blockers and no model")
        else:
            raise ValueError(f"unsupported artifact load status: {self.status}")

    @classmethod
    def ready(
        cls, manifest: ModelArtifactManifest, model: Any
    ) -> "ShadowModelArtifactLoadResult":
        return cls(status="shadow_model_ready", manifest=manifest, model=model, blockers=())

    @classmethod
    def fallback(
        cls, blocker: str, *, manifest: ModelArtifactManifest | None = None
    ) -> "ShadowModelArtifactLoadResult":
        return cls(
            status="rule_only_fallback",
            manifest=manifest,
            model=None,
            blockers=(blocker,),
        )


@dataclass(frozen=True)
class SameBytesShadowModelArtifactLoadResultV1:
    """Opt-in result that distinguishes captured and deserialized artifact bytes."""

    artifact_result: ShadowModelArtifactLoadResult
    captured_artifact_sha256: str | None
    loaded_serialized_bytes_sha256: str | None
    schema_version: str = _SAME_BYTES_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != _SAME_BYTES_SCHEMA_VERSION:
            raise ValueError("unsupported same-bytes artifact load schema")
        for field_name, value in (
            ("captured_artifact_sha256", self.captured_artifact_sha256),
            ("loaded_serialized_bytes_sha256", self.loaded_serialized_bytes_sha256),
        ):
            if value is not None and not _is_sha256(value):
                raise ValueError(f"{field_name} must be a sha256 digest")
        if (
            self.loaded_serialized_bytes_sha256 is not None
            and self.loaded_serialized_bytes_sha256 != self.captured_artifact_sha256
        ):
            raise ValueError("loaded bytes must match the captured artifact bytes")
        if (
            self.artifact_result.status == "shadow_model_ready"
            and self.loaded_serialized_bytes_sha256 is None
        ):
            raise ValueError("ready same-bytes result requires a loaded bytes digest")

    @property
    def status(self) -> str:
        return self.artifact_result.status

    @property
    def manifest(self) -> ModelArtifactManifest | None:
        return self.artifact_result.manifest

    @property
    def model(self) -> Any | None:
        return self.artifact_result.model

    @property
    def blockers(self) -> tuple[str, ...]:
        return self.artifact_result.blockers


@dataclass(frozen=True)
class SameBytesShadowModelArtifactWithManifestLoadResultV1:
    """同次 artifact 載入所用的已捕獲 manifest bytes 與驗證身分。"""

    artifact_result: SameBytesShadowModelArtifactLoadResultV1
    captured_manifest_bytes: bytes | None = field(repr=False)
    manifest_raw_bytes_sha256: str | None
    canonical_manifest_payload_sha256: str | None
    schema_version: str = _MANIFEST_SAME_BYTES_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != _MANIFEST_SAME_BYTES_SCHEMA_VERSION:
            raise ValueError("unsupported same-bytes manifest load schema")
        if self.captured_manifest_bytes is None:
            if self.manifest_raw_bytes_sha256 is not None:
                raise ValueError("manifest digest requires captured manifest bytes")
        else:
            expected_hash = _sha256_bytes(self.captured_manifest_bytes)
            if self.manifest_raw_bytes_sha256 != expected_hash:
                raise ValueError("manifest digest must match captured manifest bytes")
        if self.manifest_raw_bytes_sha256 is not None and not _is_sha256(
            self.manifest_raw_bytes_sha256
        ):
            raise ValueError("manifest digest must be a sha256 digest")
        if self.canonical_manifest_payload_sha256 is not None and not _is_sha256(
            self.canonical_manifest_payload_sha256
        ):
            raise ValueError("canonical manifest identity must be a sha256 digest")
        manifest = self.artifact_result.manifest
        if self.canonical_manifest_payload_sha256 != (
            manifest.manifest_hash if manifest is not None else None
        ):
            raise ValueError("canonical manifest identity must match the validated manifest")
        if self.artifact_result.status == "shadow_model_ready" and (
            self.captured_manifest_bytes is None
            or self.manifest_raw_bytes_sha256 is None
            or self.canonical_manifest_payload_sha256 is None
        ):
            raise ValueError("ready manifest result requires captured manifest evidence")

    @property
    def status(self) -> str:
        return self.artifact_result.status

    @property
    def manifest(self) -> ModelArtifactManifest | None:
        return self.artifact_result.manifest

    @property
    def model(self) -> Any | None:
        return self.artifact_result.model

    @property
    def blockers(self) -> tuple[str, ...]:
        return self.artifact_result.blockers

    @property
    def captured_artifact_sha256(self) -> str | None:
        return self.artifact_result.captured_artifact_sha256

    @property
    def loaded_serialized_bytes_sha256(self) -> str | None:
        return self.artifact_result.loaded_serialized_bytes_sha256


class SafeShadowModelArtifactLoader:
    def __init__(
        self,
        *,
        data_root: str | Path | None = None,
        deserializer: Callable[[Path], Any] = joblib.load,
    ) -> None:
        self._data_root = Path(
            data_root or os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
        ).resolve()
        self._deserializer = deserializer

    def load(
        self,
        artifact_root: str | Path,
        *,
        expectation: ArtifactCompatibilityExpectation,
    ) -> ShadowModelArtifactLoadResult:
        raw_root = Path(artifact_root)
        root = raw_root.resolve()
        if not raw_root.is_absolute() or root == self._data_root or self._data_root in root.parents:
            return ShadowModelArtifactLoadResult.fallback("artifact_root_not_shadow_safe")

        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            return ShadowModelArtifactLoadResult.fallback("manifest_missing")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = ModelArtifactManifest.from_dict(payload)
        except OSError:
            return ShadowModelArtifactLoadResult.fallback("manifest_read_failed")
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            return ShadowModelArtifactLoadResult.fallback(_manifest_blocker(exc))

        try:
            manifest.to_load_contract().validate(
                expected_model_family=expectation.expected_model_family,
                expected_feature_registry_hash=expectation.expected_feature_registry_hash,
                expected_label_registry_hash=expectation.expected_label_registry_hash,
                expected_feature_schema=expectation.expected_feature_schema,
                installed_library_versions=expectation.installed_library_versions,
            )
        except ValueError as exc:
            return ShadowModelArtifactLoadResult.fallback(
                _compatibility_blocker(exc), manifest=manifest
            )

        artifact_path = (root / manifest.artifact_filename).resolve()
        if artifact_path.parent != root or not artifact_path.is_file():
            return ShadowModelArtifactLoadResult.fallback(
                "artifact_missing_or_uncontrolled", manifest=manifest
            )
        if _sha256_file(artifact_path) != manifest.artifact_hash:
            return ShadowModelArtifactLoadResult.fallback(
                "artifact_hash_mismatch", manifest=manifest
            )

        try:
            model = self._deserializer(artifact_path)
        except Exception:
            return ShadowModelArtifactLoadResult.fallback(
                "artifact_deserialization_failed", manifest=manifest
            )
        if not _model_matches_manifest(model, manifest):
            return ShadowModelArtifactLoadResult.fallback(
                "deserialized_model_identity_mismatch", manifest=manifest
            )
        return ShadowModelArtifactLoadResult.ready(manifest, model)

    def load_same_bytes_v1(
        self,
        artifact_root: str | Path,
        *,
        expectation: ArtifactCompatibilityExpectation,
    ) -> SameBytesShadowModelArtifactLoadResultV1:
        """Load a single artifact from the same private buffer whose hash passed.

        This additive path is intentionally limited to the default joblib loader.
        It binds only the serialized artifact bytes, not pointer, candidate,
        manifest, lineage, source or receipt files.
        """
        if self._deserializer is not _DEFAULT_JOBLIB_LOAD:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback(
                    "verified_buffer_requires_default_joblib"
                )
            )

        try:
            raw_root = Path(artifact_root)
            root = raw_root.resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback("artifact_root_invalid")
            )
        if not raw_root.is_absolute() or root == self._data_root or self._data_root in root.parents:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback("artifact_root_not_shadow_safe")
            )

        manifest_path = root / "manifest.json"
        try:
            manifest_exists = manifest_path.is_file()
            if not manifest_exists:
                return _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback("manifest_missing")
                )
            manifest_bytes_text = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback("manifest_read_failed")
            )
        try:
            payload = json.loads(manifest_bytes_text)
            manifest = ModelArtifactManifest.from_dict(payload)
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback(_manifest_blocker(exc))
            )

        return self._load_same_bytes_from_manifest(
            root, manifest, expectation=expectation
        )

    def load_same_bytes_with_manifest_v1(
        self,
        artifact_root: str | Path,
        *,
        expectation: ArtifactCompatibilityExpectation,
    ) -> SameBytesShadowModelArtifactWithManifestLoadResultV1:
        """單次捕獲 manifest bytes，並以該 buffer 解析後載入 artifact。

        此 opt-in wrapper 為 v1 的 artifact 結果增加 manifest 原始 bytes 證據；
        呼叫端仍負責能力返回前的 manifest path bytes 複查。
        """

        if self._deserializer is not _DEFAULT_JOBLIB_LOAD:
            return _same_bytes_with_manifest_result(
                _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback(
                        "verified_buffer_requires_default_joblib"
                    )
                )
            )

        try:
            raw_root = Path(artifact_root)
            root = raw_root.resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            return _same_bytes_with_manifest_result(
                _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback("artifact_root_invalid")
                )
            )
        if not raw_root.is_absolute() or root == self._data_root or self._data_root in root.parents:
            return _same_bytes_with_manifest_result(
                _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback("artifact_root_not_shadow_safe")
                )
            )

        manifest_path = root / "manifest.json"
        try:
            if not manifest_path.is_file():
                return _same_bytes_with_manifest_result(
                    _same_bytes_result(
                        ShadowModelArtifactLoadResult.fallback("manifest_missing")
                    )
                )
            manifest_bytes = manifest_path.read_bytes()
        except OSError:
            return _same_bytes_with_manifest_result(
                _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback("manifest_read_failed")
                )
            )

        manifest_raw_hash = _sha256_bytes(manifest_bytes)
        try:
            payload = json.loads(manifest_bytes.decode("utf-8"))
            manifest = ModelArtifactManifest.from_dict(payload)
        except (AttributeError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return _same_bytes_with_manifest_result(
                _same_bytes_result(
                    ShadowModelArtifactLoadResult.fallback(_manifest_blocker(exc))
                ),
                manifest_bytes=manifest_bytes,
                manifest_raw_hash=manifest_raw_hash,
            )

        artifact_result = self._load_same_bytes_from_manifest(
            root, manifest, expectation=expectation
        )
        return _same_bytes_with_manifest_result(
            artifact_result,
            manifest_bytes=manifest_bytes,
            manifest_raw_hash=manifest_raw_hash,
            canonical_manifest_hash=manifest.manifest_hash,
        )

    def _load_same_bytes_from_manifest(
        self,
        root: Path,
        manifest: ModelArtifactManifest,
        *,
        expectation: ArtifactCompatibilityExpectation,
    ) -> SameBytesShadowModelArtifactLoadResultV1:
        """沿用既有 artifact 檢查，使用呼叫端已解析的 manifest。"""

        try:
            manifest.to_load_contract().validate(
                expected_model_family=expectation.expected_model_family,
                expected_feature_registry_hash=expectation.expected_feature_registry_hash,
                expected_label_registry_hash=expectation.expected_label_registry_hash,
                expected_feature_schema=expectation.expected_feature_schema,
                installed_library_versions=expectation.installed_library_versions,
            )
        except ValueError as exc:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback(
                    _compatibility_blocker(exc), manifest=manifest
                )
            )

        try:
            artifact_path = (root / manifest.artifact_filename).resolve()
            artifact_is_controlled_file = (
                artifact_path.parent == root and artifact_path.is_file()
            )
        except (OSError, RuntimeError, ValueError):
            artifact_is_controlled_file = False
            artifact_path = root / manifest.artifact_filename
        if not artifact_is_controlled_file:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback(
                    "artifact_missing_or_uncontrolled", manifest=manifest
                )
            )

        captured_hash: str | None = None
        loaded_hash: str | None = None
        try:
            with artifact_path.open("rb") as source, SpooledTemporaryFile(
                max_size=_SAME_BYTES_SPOOL_MEMORY_LIMIT, mode="w+b"
            ) as verified_buffer:
                digest = hashlib.sha256()
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    if verified_buffer.write(block) != len(block):
                        raise OSError("short write while capturing artifact bytes")
                    digest.update(block)
                captured_hash = f"sha256:{digest.hexdigest()}"
                if captured_hash != manifest.artifact_hash:
                    return _same_bytes_result(
                        ShadowModelArtifactLoadResult.fallback(
                            "artifact_hash_mismatch", manifest=manifest
                        ),
                        captured_hash=captured_hash,
                    )

                try:
                    artifact_path_after_capture = (
                        root / manifest.artifact_filename
                    ).resolve(strict=True)
                except (OSError, RuntimeError, ValueError):
                    artifact_path_after_capture = None
                if (
                    artifact_path_after_capture != artifact_path
                    or artifact_path_after_capture.parent != root
                ):
                    return _same_bytes_result(
                        ShadowModelArtifactLoadResult.fallback(
                            "artifact_path_changed_during_capture", manifest=manifest
                        ),
                        captured_hash=captured_hash,
                    )

                verified_buffer.seek(0)
                try:
                    model = _deserialize_verified_joblib_buffer(verified_buffer)
                except Exception:
                    return _same_bytes_result(
                        ShadowModelArtifactLoadResult.fallback(
                            "artifact_deserialization_failed", manifest=manifest
                        ),
                        captured_hash=captured_hash,
                    )
                loaded_hash = captured_hash

                try:
                    model_matches = _model_matches_manifest(model, manifest)
                except Exception:
                    model_matches = False
                if not model_matches:
                    return _same_bytes_result(
                        ShadowModelArtifactLoadResult.fallback(
                            "deserialized_model_identity_mismatch", manifest=manifest
                        ),
                        captured_hash=captured_hash,
                        loaded_hash=loaded_hash,
                    )
                return _same_bytes_result(
                    ShadowModelArtifactLoadResult.ready(manifest, model),
                    captured_hash=captured_hash,
                    loaded_hash=loaded_hash,
                )
        except OSError:
            return _same_bytes_result(
                ShadowModelArtifactLoadResult.fallback(
                    "artifact_read_failed", manifest=manifest
                ),
                captured_hash=captured_hash,
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _deserialize_verified_joblib_buffer(buffer: _VerifiedArtifactBuffer) -> Any:
    # joblib documents both paths and seekable file objects as load inputs.
    return _DEFAULT_JOBLIB_LOAD(buffer, mmap_mode=None)


def _same_bytes_result(
    result: ShadowModelArtifactLoadResult,
    *,
    captured_hash: str | None = None,
    loaded_hash: str | None = None,
) -> SameBytesShadowModelArtifactLoadResultV1:
    return SameBytesShadowModelArtifactLoadResultV1(
        artifact_result=result,
        captured_artifact_sha256=captured_hash,
        loaded_serialized_bytes_sha256=loaded_hash,
    )


def _same_bytes_with_manifest_result(
    artifact_result: SameBytesShadowModelArtifactLoadResultV1,
    *,
    manifest_bytes: bytes | None = None,
    manifest_raw_hash: str | None = None,
    canonical_manifest_hash: str | None = None,
) -> SameBytesShadowModelArtifactWithManifestLoadResultV1:
    return SameBytesShadowModelArtifactWithManifestLoadResultV1(
        artifact_result=artifact_result,
        captured_manifest_bytes=manifest_bytes,
        manifest_raw_bytes_sha256=manifest_raw_hash,
        canonical_manifest_payload_sha256=canonical_manifest_hash,
    )


def _sha256_bytes(payload: bytes) -> str:
    """回傳 bytes 的 sha256 識別值。"""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _is_sha256(value: str) -> bool:
    prefix = "sha256:"
    digest = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _model_matches_manifest(model: Any, manifest: ModelArtifactManifest) -> bool:
    return (
        getattr(model, "model_id", None) == manifest.model_id
        and getattr(model, "dataset_id", None) == manifest.dataset_id
        and getattr(model, "model_family", None) == manifest.model_family
        and getattr(model, "shadow_only", None) is True
        and getattr(model, "production_eligible", None) is False
        and getattr(model, "production_action_allowed", False) is False
    )


def _manifest_blocker(error: Exception) -> str:
    message = str(error)
    if "shadow flags" in message:
        return "manifest_shadow_flags_invalid"
    if "manifest hash" in message:
        return "manifest_hash_mismatch"
    if "schema_version" in message:
        return "manifest_schema_version_mismatch"
    return "manifest_invalid"


def _compatibility_blocker(error: ValueError) -> str:
    message = str(error)
    mappings = {
        "model family mismatch": "model_family_mismatch",
        "feature registry hash mismatch": "feature_registry_hash_mismatch",
        "label registry hash mismatch": "label_registry_hash_mismatch",
        "feature schema mismatch": "feature_schema_mismatch",
        "library version mismatch": "library_version_mismatch",
        "not shadow-only": "manifest_shadow_flags_invalid",
    }
    for fragment, blocker in mappings.items():
        if fragment in message:
            return blocker
    return "artifact_load_contract_mismatch"
