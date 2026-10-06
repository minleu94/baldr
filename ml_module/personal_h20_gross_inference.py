"""以已核 lineage 與原 same-bytes loader 讀 H20 毛報酬；不訓練、不保存。"""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import version as distribution_version
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from ml_module.model_artifact_loader import (
    ArtifactCompatibilityExpectation,
    SafeShadowModelArtifactLoader,
    SameBytesShadowModelArtifactLoadResultV1,
    SameBytesShadowModelArtifactWithManifestLoadResultV1,
    ShadowModelArtifactLoadResult,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.personal_h20_gross_model_contract import (
    H20GrossInferenceOutput,
    H20GrossInferenceRequest,
    H20GrossLineageReader,
    H20GrossModelContract,
    payload_hash,
    sha256_bytes,
    strict_date,
)


def _verify_observed_runtime(versions: Mapping[str, str]) -> None:
    """核當前 process 安裝版本；caller 提供的版本字串不是觀測證據。"""
    for library, expected in versions.items():
        if distribution_version(library) != expected:
            raise ValueError("observed_runtime_version_mismatch:" + library)


class H20GrossArtifactLoader(Protocol):
    @property
    def contract_hash(self) -> str: ...

    def load_same_bytes_with_manifest_v1(
        self, artifact_root: str | Path, *, expectation: ArtifactCompatibilityExpectation
    ) -> SameBytesShadowModelArtifactWithManifestLoadResultV1: ...


class PinnedH20GrossArtifactLoader(SafeShadowModelArtifactLoader):
    """沿原 loader 的捕獲／hash／decode，只在 decode 前增加本包精確 pins。

    原 public loader 在讀入 manifest 後才呼叫此 hook；核同一個已捕獲的
    manifest，而非事後才拒絕另一份已反序列化 artifact。不改原 loader 檔。
    """

    def __init__(self, contract: H20GrossModelContract, *, data_root: str | Path) -> None:
        super().__init__(data_root=data_root)
        self._contract = contract

    @property
    def contract_hash(self) -> str:
        return self._contract.contract_hash

    def _load_same_bytes_from_manifest(
        self, root: Path, manifest: ModelArtifactManifest, *, expectation: ArtifactCompatibilityExpectation
    ) -> SameBytesShadowModelArtifactLoadResultV1:
        c = self._contract
        try:
            if root != Path(c.artifact_root).resolve():
                raise ValueError("pinned_artifact_root_mismatch")
            if (manifest.manifest_hash != c.manifest_hash or manifest.artifact_hash != c.artifact_hash or
                dict(manifest.library_versions) != dict(c.installed_library_versions)):
                raise ValueError("pinned_manifest_or_runtime_mismatch")
            _verify_observed_runtime(c.installed_library_versions)
            for path, expected in ((root / "manifest.json", c.manifest_raw_sha256),
                                   (root / "candidate.json", c.candidate_raw_sha256),
                                   (Path(c.lineage_path), c.lineage_raw_sha256)):
                PersonalH20GrossInference._read(path, expected)
        except (OSError, ValueError) as exc:
            return SameBytesShadowModelArtifactLoadResultV1(
                ShadowModelArtifactLoadResult.fallback("h20_predecode_pin_rejected:" + str(exc), manifest=manifest), None, None
            )
        return super()._load_same_bytes_from_manifest(root, manifest, expectation=expectation)


class PersonalH20GrossInference:
    """每次請求核原 sidecars、時間與模型 pins，失配回傳可保存的缺件結果。

    reader 必須來自受控 composition 的可信 lineage verifier；任意 callable
    並不構成來源權威。caller 亦須核 request 的 feature snapshot/source pins。
    自然樣本成熟度不在此介面當載入門檻。
    """

    def __init__(self, contract: H20GrossModelContract, *,
                 lineage_reader: H20GrossLineageReader | None,
                 artifact_loader: H20GrossArtifactLoader | None) -> None:
        self.contract = contract
        self._lineage_reader = lineage_reader
        self._artifact_loader = artifact_loader

    def predict(self, request: H20GrossInferenceRequest) -> H20GrossInferenceOutput:
        contract = self.contract
        if request.model_contract_hash != contract.contract_hash:
            return self._result(request, blocker="model_contract_hash_mismatch")
        if request.feature_schema != contract.feature_schema:
            return self._result(request, blocker="exact_feature_schema_mismatch")
        if strict_date(contract.training_as_of) > strict_date(request.decision_date):
            return self._result(request, blocker="model_not_available_at_decision")
        if not callable(self._lineage_reader) or self._artifact_loader is None:
            return self._result(request, blocker="controlled_loader_or_lineage_reader_missing")
        if getattr(self._artifact_loader, "contract_hash", None) != contract.contract_hash:
            return self._result(request, blocker="pinned_same_bytes_loader_required")
        load = getattr(self._artifact_loader, "load_same_bytes_with_manifest_v1", None)
        if not callable(load):
            return self._result(request, blocker="same_bytes_loader_required")
        try:
            root = Path(contract.artifact_root)
            manifest_bytes = self._read(root / "manifest.json", contract.manifest_raw_sha256)
            candidate_bytes = self._read(root / "candidate.json", contract.candidate_raw_sha256)
            lineage_bytes = self._read(Path(contract.lineage_path), contract.lineage_raw_sha256)
            manifest = ModelArtifactManifest.from_dict(self._object(manifest_bytes))
            candidate = self._object(candidate_bytes)
            self._validate_manifest(manifest, request)
            self._validate_candidate(candidate, manifest)
            verified = self._lineage_reader(
                contract.lineage_path, expected_manifest_hash=contract.lineage_hash,
                expected_dataset_hash=contract.dataset_hash, expected_candidate_id=contract.candidate_id,
            )
            lineage = self._object(lineage_bytes)
            lineage_body = dict(lineage)
            lineage_body.pop("manifest_hash", None)
            if (verified.manifest_hash != contract.lineage_hash or
                lineage.get("manifest_hash") != contract.lineage_hash or
                payload_hash(lineage_body) != contract.lineage_hash or
                dict(verified.payload) != lineage_body):
                raise ValueError("verified_lineage_bytes_mismatch")
            self._validate_lineage(lineage_body)
            # sidecar 可在 verifier 呼叫時改變，須於反序列化前再核。
            self._check_sidecars(root)
            loaded = load(root, expectation=self._expectation())
            if loaded.status != "shadow_model_ready":
                return self._result(request, blocker="artifact_loader_rejected:" + ",".join(loaded.blockers))
            if (loaded.manifest != manifest or loaded.captured_manifest_bytes != manifest_bytes or
                loaded.manifest_raw_bytes_sha256 != contract.manifest_raw_sha256 or
                loaded.canonical_manifest_payload_sha256 != contract.manifest_hash or
                loaded.captured_artifact_sha256 != contract.artifact_hash or
                loaded.loaded_serialized_bytes_sha256 != contract.artifact_hash):
                raise ValueError("same_bytes_identity_mismatch")
            # loader 返回後仍需確認原捕獲 sidecars 未被替換。
            self._check_sidecars(root)
            model = loaded.model
            self._validate_model(model)
            prediction = model.predict(request.feature_values)
            for field, expected in (("model_id", contract.model_id), ("dataset_id", contract.dataset_id),
                                    ("training_as_of", contract.training_as_of), ("horizon_trading_days", 20)):
                actual = getattr(prediction, field, None)
                if actual != expected or (field == "horizon_trading_days" and type(actual) is not int):
                    raise ValueError("prediction_identity_mismatch:" + field)
            value = getattr(prediction, "ranking_score_bp", None)
            if type(value) is not int or not -2_147_483_648 <= value <= 2_147_483_647:
                raise ValueError("gross_head_requires_integer_bp")
            self._check_sidecars(root)
            return self._result(request, value=value)
        except Exception as exc:
            # 不吞 KeyboardInterrupt/SystemExit；缺件不造零值，也不冒稱資格。
            blocker = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            return self._result(request, blocker="h20_contract_rejected:" + blocker)

    def _expectation(self) -> ArtifactCompatibilityExpectation:
        c = self.contract
        return ArtifactCompatibilityExpectation(c.model_family, c.feature_registry_hash,
            c.label_registry_hash, c.feature_schema, c.installed_library_versions)

    def _validate_manifest(self, manifest: ModelArtifactManifest, request: H20GrossInferenceRequest) -> None:
        c = self.contract
        for field in ("model_id", "dataset_id", "model_family", "feature_schema", "feature_registry_hash",
                      "label_registry_hash", "training_as_of", "artifact_hash", "manifest_hash"):
            if getattr(manifest, field) != getattr(c, field):
                raise ValueError("manifest_identity_mismatch:" + field)
        manifest.to_load_contract().validate(
            expected_model_family=c.model_family, expected_feature_registry_hash=c.feature_registry_hash,
            expected_label_registry_hash=c.label_registry_hash, expected_feature_schema=c.feature_schema,
            installed_library_versions=c.installed_library_versions,
        )
        # 原 loader 僅 major.minor 相容；本 typed view 明示要求完整版本相等。
        if dict(manifest.library_versions) != dict(c.installed_library_versions):
            raise ValueError("exact_runtime_version_mismatch")
        _verify_observed_runtime(c.installed_library_versions)
        created = datetime.fromisoformat(manifest.created_at.replace("Z", "+00:00"))
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("model_creation_clock_unknown")
        if created.date() > strict_date(request.decision_date):
            raise ValueError("model_created_after_decision")

    def _validate_candidate(self, candidate: Mapping[str, Any], manifest: ModelArtifactManifest) -> None:
        c = self.contract
        if candidate.get("schema_version") != "recommendation-calibration-candidate.v1":
            raise ValueError("unsupported_gross_head_adapter")
        unknown = {"legacy_unproven", "training_lineage_missing"}
        if (any(candidate.get(field) in unknown for field in ("lineage_status", "model_status", "qualification_status")) or
            any(item in unknown for item in candidate.get("candidate_blockers", ()))):
            raise ValueError("candidate_lineage_unproven")
        for field in ("candidate_id", "model_id", "model_version", "dataset_id", "dataset_hash", "model_family",
                      "feature_registry_hash", "label_registry_hash", "manifest_hash", "artifact_hash", "training_as_of"):
            if candidate.get(field) != getattr(c, field):
                raise ValueError("candidate_identity_mismatch:" + field)
        if candidate.get("feature_schema") != [list(row) for row in c.feature_schema] or candidate.get("feature_names") != [row[0] for row in c.feature_schema]:
            raise ValueError("candidate_exact_features_mismatch")
        if candidate.get("feature_schema_hash") != payload_hash({"feature_schema": [list(row) for row in c.feature_schema]}):
            raise ValueError("candidate_feature_schema_hash_mismatch")
        if type(candidate.get("horizon_trading_days")) is not int or candidate["horizon_trading_days"] != 20:
            raise ValueError("candidate_horizon_mismatch")
        if candidate.get("return_basis") != c.price_basis:
            raise ValueError("candidate_price_basis_mismatch")
        if candidate.get("label_contract_id") not in (
            "recommendation-absolute-labels-v1", "recommendation-absolute-labels-banktaiwan-estimated-v1"
        ):
            raise ValueError("candidate_target_mismatch")
        if candidate.get("target_definitions", {}).get("upside") != "absolute forward stock return over 20 trading days > 0 bp":
            raise ValueError("candidate_gross_target_unproven")
        if candidate.get("candidate_frozen_at") != manifest.created_at:
            raise ValueError("candidate_creation_clock_mismatch")
        if (candidate.get("shadow_only") is not True or candidate.get("production_eligible") is not False or
            candidate.get("production_action_allowed") is not False):
            raise ValueError("candidate_qualification_flags_invalid")

    def _validate_lineage(self, lineage: Mapping[str, Any]) -> None:
        c = self.contract
        if lineage.get("schema_version") != "recommendation-training-lineage.v1":
            raise ValueError("training_lineage_missing")
        for field, expected in (("candidate_id", c.candidate_id), ("dataset_id", c.dataset_id),
            ("dataset_hash", c.dataset_hash), ("candidate_manifest_hash", c.manifest_hash),
            ("candidate_artifact_hash", c.artifact_hash), ("training_as_of", c.training_as_of),
            ("training_source_hash", c.training_source_hash), ("training_pit_hash", c.training_pit_hash),
            ("feature_registry_hash", c.feature_registry_hash), ("return_basis", c.price_basis)):
            if lineage.get(field) != expected:
                raise ValueError("lineage_identity_mismatch:" + field)
        if lineage.get("feature_schema") != [list(row) for row in c.feature_schema]:
            raise ValueError("lineage_exact_features_mismatch")
        context = lineage.get("training_context", {})
        if context.get("semantics") != "decision_time" or context.get("decision_time_eligible") is not True:
            raise ValueError("lineage_not_decision_time_eligible")
        if not lineage.get("merged_samples"):
            raise ValueError("training_lineage_has_no_samples")

    def _validate_model(self, model: Any) -> None:
        c = self.contract
        for field in ("model_id", "dataset_id", "model_family", "feature_schema", "training_as_of"):
            if getattr(model, field, None) != getattr(c, field):
                raise ValueError("model_identity_mismatch:" + field)
        if getattr(model, "feature_names", None) != tuple(row[0] for row in c.feature_schema):
            raise ValueError("model_feature_order_mismatch")
        if type(getattr(model, "horizon_trading_days", None)) is not int or model.horizon_trading_days != 20:
            raise ValueError("model_horizon_mismatch")
        if not callable(getattr(getattr(model, "return_model", None), "predict", None)):
            raise ValueError("gross_head_missing")
        if not callable(getattr(model, "predict", None)):
            raise ValueError("model_prediction_api_missing")
        if (getattr(model, "shadow_only", None) is not True or getattr(model, "production_eligible", None) is not False or
            getattr(model, "production_action_allowed", None) is not False):
            raise ValueError("model_qualification_flags_invalid")

    def _check_sidecars(self, root: Path) -> None:
        c = self.contract
        self._read(root / "manifest.json", c.manifest_raw_sha256)
        self._read(root / "candidate.json", c.candidate_raw_sha256)
        self._read(Path(c.lineage_path), c.lineage_raw_sha256)

    @staticmethod
    def _read(path: Path, expected_hash: str) -> bytes:
        # 只讀 sidecars；限制單檔 64 MiB，避免無界 JSON capture。
        with path.open("rb") as handle:
            raw = handle.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("sidecar_read_budget_exceeded")
        if sha256_bytes(raw) != expected_hash:
            raise ValueError("sidecar_hash_mismatch:" + path.name)
        return raw

    @staticmethod
    def _object(raw: bytes) -> Mapping[str, Any]:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("sidecar_requires_object")
        return payload

    def _result(self, request: H20GrossInferenceRequest, *, value: int | None = None,
                blocker: str | None = None) -> H20GrossInferenceOutput:
        c = self.contract
        return H20GrossInferenceOutput(request, "h20_gross_unavailable" if blocker else "h20_gross_available",
            value, c.model_id, c.model_version, c.contract_hash, c.artifact_hash, c.lineage_hash,
            (blocker,) if blocker else ())
