"""私人 H20 毛報酬讀模型契約；不改既有 calibration 或授予交易資格。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol


H20_GROSS_CONTRACT_VERSION = "personal-h20-gross.v1"
H20_GROSS_TARGET = "absolute_forward_stock_return_bp"
H20_GROSS_PRICE_BASIS = "close_to_close_event_date"
H20_GROSS_COST_BASIS = "no_cost_gross"
H20_GROSS_ADAPTER = "recommendation-calibration-return-head.v1"
FeatureSchema = tuple[tuple[str, str, str], ...]


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def payload_hash(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def require_hash(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{field}: invalid_sha256")
    if any(char not in "0123456789abcdef" for char in value[7:]):
        raise ValueError(f"{field}: invalid_sha256")


def strict_date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date_requires_iso_day")
    return parsed


def validate_schema(schema: FeatureSchema) -> None:
    if not isinstance(schema, tuple) or not schema:
        raise ValueError("exact_feature_schema_required")
    if any(not isinstance(row, tuple) or len(row) != 3 or
           any(not isinstance(item, str) or not item.strip() for item in row) for row in schema):
        raise ValueError("invalid_feature_schema")
    if len({row[0] for row in schema}) != len(schema):
        raise ValueError("duplicate_feature_name")


@dataclass(frozen=True)
class H20GrossModelContract:
    """中央核定的精確 artifact/lineage pins；hash 不是來源可信度證明。"""

    artifact_root: str
    lineage_path: str
    model_id: str
    model_version: str
    dataset_id: str
    dataset_hash: str
    candidate_id: str
    model_family: str
    feature_schema: FeatureSchema
    feature_registry_hash: str
    label_registry_hash: str
    manifest_hash: str
    manifest_raw_sha256: str
    artifact_hash: str
    candidate_raw_sha256: str
    lineage_hash: str
    lineage_raw_sha256: str
    training_source_hash: str
    training_pit_hash: str
    training_as_of: str
    installed_library_versions: Mapping[str, str]
    target: str = H20_GROSS_TARGET
    horizon_trading_days: int = 20
    price_basis: str = H20_GROSS_PRICE_BASIS
    cost_basis: str = H20_GROSS_COST_BASIS
    adapter_version: str = H20_GROSS_ADAPTER
    contract_version: str = H20_GROSS_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field in ("artifact_root", "lineage_path", "model_id", "model_version", "dataset_id",
                      "candidate_id", "model_family"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field}: required")
        if not Path(self.artifact_root).is_absolute() or not Path(self.lineage_path).is_absolute():
            raise ValueError("absolute_artifact_and_lineage_paths_required")
        for field in ("dataset_hash", "feature_registry_hash", "label_registry_hash", "manifest_hash",
                      "manifest_raw_sha256", "artifact_hash", "candidate_raw_sha256", "lineage_hash",
                      "lineage_raw_sha256", "training_source_hash", "training_pit_hash"):
            require_hash(getattr(self, field), field)
        validate_schema(self.feature_schema)
        strict_date(self.training_as_of)
        if self.target != H20_GROSS_TARGET or type(self.horizon_trading_days) is not int or self.horizon_trading_days != 20:
            raise ValueError("target_or_horizon_mismatch")
        if (self.price_basis, self.cost_basis) != (H20_GROSS_PRICE_BASIS, H20_GROSS_COST_BASIS):
            raise ValueError("price_or_cost_basis_mismatch")
        if (self.adapter_version, self.contract_version) != (H20_GROSS_ADAPTER, H20_GROSS_CONTRACT_VERSION):
            raise ValueError("contract_version_mismatch")
        versions = dict(self.installed_library_versions)
        if not versions or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in versions.items()):
            raise ValueError("runtime_versions_required")
        object.__setattr__(self, "installed_library_versions", MappingProxyType(versions))

    @property
    def contract_hash(self) -> str:
        # MappingProxyType 不可 deepcopy，先明示展開；其餘欄位都是 immutable 值。
        return payload_hash({field: (dict(value) if field == "installed_library_versions" else value)
                             for field, value in vars(self).items()})

    @property
    def capture_model_version(self) -> str:
        """原 canonical capture 的 model_version 是 candidate_id，保留原語義。"""
        return self.candidate_id


@dataclass(frozen=True)
class H20GrossInferenceRequest:
    symbol: str
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    feature_schema: FeatureSchema
    feature_values: tuple[int | None, ...]
    feature_snapshot_hash: str
    feature_source_hash: str
    model_contract_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol_required")
        decision = strict_date(self.decision_date)
        if strict_date(self.feature_as_of_date) >= decision or strict_date(self.feature_available_date) > decision:
            raise ValueError("feature_cutoff_violation")
        validate_schema(self.feature_schema)
        if not isinstance(self.feature_values, tuple) or len(self.feature_values) != len(self.feature_schema):
            raise ValueError("feature_vector_mismatch")
        if any(value is not None and type(value) is not int for value in self.feature_values):
            raise TypeError("feature_values_require_integer_or_missing")
        for field in ("feature_snapshot_hash", "feature_source_hash", "model_contract_hash"):
            require_hash(getattr(self, field), field)


@dataclass(frozen=True)
class H20GrossInferenceOutput:
    request: H20GrossInferenceRequest
    status: str
    predicted_gross_return_bp: int | None
    model_id: str
    model_version: str
    model_contract_hash: str
    artifact_hash: str
    lineage_hash: str
    blockers: tuple[str, ...] = ()
    target: str = H20_GROSS_TARGET
    horizon_trading_days: int = 20
    price_basis: str = H20_GROSS_PRICE_BASIS
    cost_basis: str = H20_GROSS_COST_BASIS
    contract_version: str = H20_GROSS_CONTRACT_VERSION
    formal_eligible: bool = False
    natural_evidence_eligible: bool = False
    production_action_allowed: bool = False

    def __post_init__(self) -> None:
        if self.status == "h20_gross_available":
            if type(self.predicted_gross_return_bp) is not int or self.blockers:
                raise ValueError("available_requires_integer_prediction")
        elif self.status == "h20_gross_unavailable":
            if self.predicted_gross_return_bp is not None or not self.blockers:
                raise ValueError("unavailable_requires_blocker_and_missing_prediction")
        else:
            raise ValueError("invalid_h20_status")
        if (self.target, self.horizon_trading_days, self.price_basis, self.cost_basis, self.contract_version) != (
            H20_GROSS_TARGET, 20, H20_GROSS_PRICE_BASIS, H20_GROSS_COST_BASIS, H20_GROSS_CONTRACT_VERSION
        ) or type(self.horizon_trading_days) is not int:
            raise ValueError("output_contract_mismatch")
        if any(value is not False for value in (self.formal_eligible, self.natural_evidence_eligible, self.production_action_allowed)):
            raise ValueError("output_cannot_grant_qualification")
        for field in ("model_contract_hash", "artifact_hash", "lineage_hash"):
            require_hash(getattr(self, field), field)
        if self.status == "h20_gross_available" and self.request.model_contract_hash != self.model_contract_hash:
            raise ValueError("request_output_contract_mismatch")

    @property
    def prediction_id(self) -> str:
        return "personal-h20:" + payload_hash(asdict(self.request))[7:]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "prediction_id": self.prediction_id}


class VerifiedTrainingLineage(Protocol):
    @property
    def payload(self) -> Mapping[str, Any]: ...

    @property
    def manifest_hash(self) -> str: ...


class H20GrossLineageReader(Protocol):
    """由 composition 注入原可信 lineage reader；不接受候選自稱 verified。"""

    def __call__(self, path: str | Path, *, expected_manifest_hash: str | None = None,
                 expected_dataset_hash: str | None = None,
                 expected_candidate_id: str | None = None) -> VerifiedTrainingLineage: ...


class H20GrossInferencePort(Protocol):
    def predict(self, request: H20GrossInferenceRequest) -> H20GrossInferenceOutput: ...
