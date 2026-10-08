"""真正的 forward prediction capture 與成熟 outcome comparison producer。

Capture 只寫在 decision cutoff 當下可取得的 feature、candidate/champion
prediction 與 immutable candidate identity；它不包含未來 label。等到 outcome
自然成熟後，``NaturalForwardEvidenceBuilder`` 才讀取 capture 與 matured
outcomes，重算同樣本、同成本的 metrics 並產生可驗證 receipt。這條路徑與
historical untouched test 完全分離，不能用歷史考卷冒充自然前瞻證據。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np

from ml_module.current_observed_feature_snapshot_composer import ScheduledSnapshotSourceBindingVerifier

from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.recommendation_calibration_authority import RecommendationPromotionPolicy
from ml_module.recommendation_calibration_inference_contract import (
    FrozenRecommendationInference,
)
from ml_module.recommendation_calibration_training import (
    RecommendationPrediction,
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
    feature_schema_hash,
    candidate_freeze_hash,
)
from ml_module.recommendation_cost_scenario import (
    LEGACY_RECOMMENDATION_COST_SCENARIO_ID,
    LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION,
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
    normalize_cost_scenario,
)
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
    PROBABILITY_TRANSFORM_ID,
    RecommendationProbabilityTransform,
)
from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)
from data_module.current_observed_capacity_eligibility import (
    classify_current_observed_raw_status,
    current_stock_research_capacity_passed,
)
from data_module.pinned_sqlite_read_session import (
    PinnedSQLiteReadSession,
    SQLiteFilePinV1,
)


_CURRENT_OBSERVED_RESEARCH_ROOT = (
    Path(__file__).resolve().parents[1] / "output" / "ml_research"
)


def _current_observed_research_roots() -> tuple[Path, ...]:
    """Return exact legacy and active roots for pinned current-observed reads."""

    legacy_root = Path(_CURRENT_OBSERVED_RESEARCH_ROOT)
    repository_root = legacy_root.parents[1]
    roots: list[Path] = []
    for candidate in (
        legacy_root,
        get_ml_research_root(repository_root=repository_root),
    ):
        resolved = resolve_ml_research_output_path(
            candidate,
            repository_root=repository_root,
            access="read",
        )
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _is_below_current_observed_cycle_root(
    path: Path, research_roots: Sequence[Path]
) -> bool:
    return any(
        _path_is_same_or_child(path, root / "current_stock_cycles")
        for root in research_roots
    )


def _current_observed_research_root_for_path(
    path: Path, research_roots: Sequence[Path]
) -> Path | None:
    """Return the sole approved research root containing a pinned artifact."""

    matches = [root for root in research_roots if _path_is_same_or_child(path, root)]
    return matches[0] if len(matches) == 1 else None


def _path_is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class RecommendationPredictionCaptureInput:
    row_id: str
    symbol: str
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    feature_values: tuple[int | None, ...]
    rule_probability_bp: int
    rule_after_cost_probability_bp: int | None = None
    rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID

    def __post_init__(self) -> None:
        if not self.row_id.strip() or not self.symbol.strip():
            raise ValueError("capture row_id and symbol are required")
        decision = _date(self.decision_date)
        if _date(self.feature_as_of_date) >= decision:
            raise ValueError("capture feature_as_of_date must be before decision_date")
        if _date(self.feature_available_date) > decision:
            raise ValueError("capture feature_available_date must not be later than decision_date")
        _probability(self.rule_probability_bp, "rule_probability_bp")
        if not self.rule_baseline_id.strip():
            raise ValueError("rule_baseline_id is required")
        if self.rule_after_cost_probability_bp is not None:
            _probability(self.rule_after_cost_probability_bp, "rule_after_cost_probability_bp")


@dataclass(frozen=True)
class RecommendationPredictionCapture:
    capture_id: str
    capture_as_of_date: str
    captured_at: str
    candidate_id: str
    candidate_root: str
    candidate_freeze_hash: str
    candidate_frozen_at: str
    candidate_manifest_hash: str
    candidate_artifact_hash: str
    dataset_hash: str
    feature_registry_hash: str
    feature_schema_hash: str
    feature_schema: FeatureSchema
    label_registry_hash: str
    cost_contract_hash: str
    fixed_round_trip_cost_bp: int | None
    maximum_probability_change_bp: int
    policy_hash: str
    rows: tuple[Mapping[str, Any], ...]
    capture_hash: str
    probability_transform_id: str = PROBABILITY_TRANSFORM_ID
    probability_baseline_id: str = NULL_BENCHMARK_BASELINE_ID
    probability_baseline_kind: str = "null_benchmark"
    probability_lineage: tuple[Mapping[str, Any], ...] = ()
    champion_model_id: str = ""
    champion_candidate_id: str = ""
    champion_candidate_root: str = ""
    champion_manifest_hash: str = ""
    champion_artifact_hash: str = ""
    champion_freeze_hash: str = ""
    champion_pointer_version: int | None = None
    capture_path: str | None = None
    capture_origin: str = "scheduled_live"
    source_contract_binding: Mapping[str, Any] | None = None
    schema_version: str = "recommendation-prediction-capture.v2"
    cost_scenario_id: str = LEGACY_RECOMMENDATION_COST_SCENARIO_ID
    cost_scenario_version: str = LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION
    cost_scenario_hash: str = ""
    cost_basis: str = "fixed_round_trip_bp"
    cost_policy_id: str | None = None
    cost_policy_version: str | None = None
    policy_estimate_date: str | None = None
    research_order_amount_twd: str | None = None
    research_order_quantity_shares: int | None = None
    lot_type: str | None = None
    instrument_type: str | None = None
    cost_scenario: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "candidate_id": self.candidate_id,
            "candidate_root": self.candidate_root,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "candidate_frozen_at": self.candidate_frozen_at,
            "candidate_manifest_hash": self.candidate_manifest_hash,
            "candidate_artifact_hash": self.candidate_artifact_hash,
            "dataset_hash": self.dataset_hash,
            "feature_registry_hash": self.feature_registry_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "feature_schema": [list(item) for item in self.feature_schema],
            "label_registry_hash": self.label_registry_hash,
            "cost_contract_hash": self.cost_contract_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "policy_hash": self.policy_hash,
            "rows": [dict(row) for row in self.rows],
            "capture_hash": self.capture_hash,
            "probability_transform_id": self.probability_transform_id,
            "probability_baseline_id": self.probability_baseline_id,
            "probability_baseline_kind": self.probability_baseline_kind,
            "probability_lineage": [dict(item) for item in self.probability_lineage],
            "champion_model_id": self.champion_model_id,
            "champion_candidate_id": self.champion_candidate_id,
            "champion_candidate_root": self.champion_candidate_root,
            "champion_manifest_hash": self.champion_manifest_hash,
            "champion_artifact_hash": self.champion_artifact_hash,
            "champion_freeze_hash": self.champion_freeze_hash,
            "champion_pointer_version": self.champion_pointer_version,
            "capture_path": self.capture_path,
            "capture_origin": self.capture_origin,
            "source_contract_binding": (
                dict(self.source_contract_binding)
                if self.source_contract_binding is not None
                else None
            ),
        }
        if self.schema_version != "recommendation-prediction-capture.v2":
            payload.update(_scenario_fields_from_capture(self))
        return payload

    def persist(self, path: str | Path) -> Path:
        destination = Path(path).resolve()
        object.__setattr__(self, "capture_path", str(destination))
        _write_json_once(destination, self.to_dict())
        return destination


@dataclass(frozen=True)
class RecommendationPredictionCaptureVerification:
    """公開唯讀 capture gate 的 typed 結果。"""

    capture_id: str
    candidate_id: str
    capture_as_of_date: str
    captured_at: str
    capture_origin: str
    capture_hash: str
    row_count: int
    cost_basis: str
    cost_scenario_id: str
    cost_scenario_version: str
    cost_scenario_hash: str
    fixed_round_trip_cost_bp: int | None
    source_contract_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-prediction-capture-verification.v1",
            "status": "verified",
            "capture_id": self.capture_id,
            "candidate_id": self.candidate_id,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "capture_origin": self.capture_origin,
            "capture_hash": self.capture_hash,
            "row_count": self.row_count,
            "cost_basis": self.cost_basis,
            "cost_scenario_id": self.cost_scenario_id,
            "cost_scenario_version": self.cost_scenario_version,
            "cost_scenario_hash": self.cost_scenario_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "source_contract_status": self.source_contract_status,
        }


@dataclass(frozen=True)
class ActiveModelPredictionCapture:
    """一個已 active pointer 的有效輸出觀測，與 challenger capture 分離。"""

    capture_id: str
    capture_as_of_date: str
    captured_at: str
    active_identity: Mapping[str, Any]
    active_identity_hash: str
    active_candidate_id: str
    active_model_id: str
    active_candidate_root: str
    active_candidate_frozen_at: str
    active_manifest_hash: str
    active_artifact_hash: str
    active_freeze_hash: str
    active_dataset_hash: str | None
    active_pointer_version: int
    active_effective_date: str
    feature_registry_hash: str
    feature_schema_hash: str
    feature_schema: FeatureSchema
    label_registry_hash: str
    cost_contract_hash: str
    fixed_round_trip_cost_bp: int | None
    maximum_probability_change_bp: int
    policy_hash: str
    probability_transform_id: str
    probability_lineage: tuple[Mapping[str, Any], ...]
    rows: tuple[Mapping[str, Any], ...]
    capture_hash: str
    capture_path: str | None = None
    capture_origin: str = "scheduled_active_monitor"
    schema_version: str = "recommendation-active-model-prediction-capture.v1"
    cost_scenario_id: str = LEGACY_RECOMMENDATION_COST_SCENARIO_ID
    cost_scenario_version: str = LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION
    cost_scenario_hash: str = ""
    cost_basis: str = "fixed_round_trip_bp"
    cost_policy_id: str | None = None
    cost_policy_version: str | None = None
    policy_estimate_date: str | None = None
    research_order_amount_twd: str | None = None
    research_order_quantity_shares: int | None = None
    lot_type: str | None = None
    instrument_type: str | None = None
    cost_scenario: Mapping[str, Any] | None = None
    source_contract_binding: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "active_identity": dict(self.active_identity),
            "active_identity_hash": self.active_identity_hash,
            "active_candidate_id": self.active_candidate_id,
            "active_model_id": self.active_model_id,
            "active_candidate_root": self.active_candidate_root,
            "active_candidate_frozen_at": self.active_candidate_frozen_at,
            "active_manifest_hash": self.active_manifest_hash,
            "active_artifact_hash": self.active_artifact_hash,
            "active_freeze_hash": self.active_freeze_hash,
            "active_dataset_hash": self.active_dataset_hash,
            "active_pointer_version": self.active_pointer_version,
            "active_effective_date": self.active_effective_date,
            "feature_registry_hash": self.feature_registry_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "feature_schema": [list(item) for item in self.feature_schema],
            "label_registry_hash": self.label_registry_hash,
            "cost_contract_hash": self.cost_contract_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "policy_hash": self.policy_hash,
            "probability_transform_id": self.probability_transform_id,
            "probability_lineage": [dict(item) for item in self.probability_lineage],
            "rows": [dict(row) for row in self.rows],
            "capture_hash": self.capture_hash,
            "capture_path": self.capture_path,
            "capture_origin": self.capture_origin,
        }
        if self.schema_version != "recommendation-active-model-prediction-capture.v1":
            payload.update(_scenario_fields_from_capture(self))
        if self.source_contract_binding is not None:
            payload["source_contract_binding"] = dict(self.source_contract_binding)
        return payload

    def persist(self, path: str | Path) -> Path:
        destination = Path(path).resolve()
        object.__setattr__(self, "capture_path", str(destination))
        _write_json_once(destination, self.to_dict())
        return destination


class ActiveModelPredictionCaptureService:
    """Capture only the currently delivered active model output for drift monitoring."""

    def capture(
        self,
        *,
        consumer: Any,
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        policy_hash: str,
        decision_date: str,
        captured_at: str,
        inputs: Sequence[RecommendationPredictionCaptureInput],
        fixed_round_trip_cost_bp: int | None,
        cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
        maximum_probability_change_bp: int = 1_000,
        source_contract_binding: Mapping[str, Any] | None = None,
        source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    ) -> ActiveModelPredictionCapture:
        capture_day = _date(decision_date).isoformat()
        if _date(captured_at) > _date(decision_date):
            raise ValueError("active model capture must not be after decision cutoff")
        if not inputs:
            raise ValueError("active model capture requires at least one input row")
        if consumer.reload(decision_date=capture_day) != "active":
            raise ValueError("active pointer is unavailable for monitoring capture")
        identity = consumer.active_identity(decision_date=capture_day)
        if not isinstance(identity, Mapping):
            raise ValueError("active pointer identity is unavailable")
        candidate_id = str(identity.get("candidate_id") or "")
        model_id = str(identity.get("model_id") or candidate_id)
        candidate_root = Path(str(identity.get("candidate_root") or "")).resolve()
        if not candidate_id or not model_id or not candidate_root.is_dir():
            raise ValueError("active pointer identity is incomplete")
        candidate_payload = _read_json(candidate_root / "candidate.json")
        manifest_payload = _read_json(candidate_root / "manifest.json")
        scenario_metadata = dict(candidate_payload)
        for key in (
            "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
            "cost_basis", "cost_policy_id", "cost_policy_version",
            "policy_estimate_date", "research_order_amount_twd",
            "research_order_quantity_shares", "lot_type", "instrument_type",
            "cost_scenario", "fixed_round_trip_cost_bp",
        ):
            if key in identity:
                scenario_metadata[key] = identity[key]
        try:
            declared_scenario = cost_scenario_from_metadata(
                scenario_metadata,
                fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            )
            resolved_scenario = (
                declared_scenario
                if cost_scenario is None
                else normalize_cost_scenario(
                    cost_scenario,
                    fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
                )
            )
        except RecommendationCostScenarioError as exc:
            raise ValueError(str(exc)) from exc
        if resolved_scenario.is_estimated and fixed_round_trip_cost_bp is not None:
            raise ValueError("estimated active capture must not carry fixed_round_trip_cost_bp")
        if (
            not resolved_scenario.is_estimated
            and fixed_round_trip_cost_bp is not None
            and resolved_scenario.fixed_round_trip_cost_bp != fixed_round_trip_cost_bp
        ):
            raise ValueError("active capture fixed cost does not match cost scenario")
        if resolved_scenario.scenario_hash != declared_scenario.scenario_hash:
            raise ValueError("active capture cost scenario does not match candidate")
        identity_scenario_hash = str(identity.get("cost_scenario_hash") or "")
        if identity_scenario_hash and identity_scenario_hash != resolved_scenario.scenario_hash:
            raise ValueError("active identity cost scenario mismatch")
        expected_label_registry_hash = str(
            identity.get("label_registry_hash")
            or candidate_payload.get("label_registry_hash")
            or ""
        )
        if not expected_label_registry_hash:
            raise ValueError("active candidate label registry hash is missing")
        candidate_frozen_at = str(manifest_payload.get("created_at") or "")
        if not candidate_frozen_at:
            raise ValueError("active candidate freeze timestamp is missing")
        if _datetime(candidate_frozen_at) > _datetime(captured_at):
            raise ValueError("active candidate freeze must precede monitoring capture")
        if str(candidate_payload.get("candidate_id") or "") != candidate_id:
            raise ValueError("active candidate identity mismatch")
        if str(manifest_payload.get("manifest_hash") or "") != str(identity.get("candidate_manifest_hash") or ""):
            raise ValueError("active candidate manifest hash mismatch")
        if str(manifest_payload.get("artifact_hash") or "") != str(identity.get("candidate_artifact_hash") or ""):
            raise ValueError("active candidate artifact hash mismatch")
        if tuple(tuple(item) for item in manifest_payload.get("feature_schema", ())) != feature_schema:
            raise ValueError("active candidate feature schema mismatch")
        lineage_payload = identity.get("probability_lineage")
        if not isinstance(lineage_payload, list) or not lineage_payload:
            raise ValueError("active probability lineage is missing")
        lineage = tuple(dict(item) for item in lineage_payload if isinstance(item, Mapping))
        if len(lineage) != len(lineage_payload):
            raise ValueError("active probability lineage is invalid")
        rows: list[Mapping[str, Any]] = []
        for item in sorted(inputs, key=lambda row: (row.row_id, row.symbol)):
            if _date(item.decision_date) != _date(decision_date):
                raise ValueError("all active monitoring rows must use capture decision_date")
            projection = consumer.project(
                stock_code=item.symbol,
                feature_values=item.feature_values,
                rule_probability_bp=item.rule_probability_bp,
                after_cost_rule_probability_bp=item.rule_after_cost_probability_bp,
                rule_baseline_id=item.rule_baseline_id,
                decision_date=capture_day,
                data_quality="observed",
            )
            if projection.status != "active_candidate" or projection.calibrated_probability_bp is None:
                raise ValueError("active effective probability is unavailable")
            if projection.raw_calibrated_probability_bp is None:
                raise ValueError("active raw probability is unavailable")
            rows.append(
                {
                    "row_id": item.row_id,
                    "symbol": item.symbol,
                    "decision_date": capture_day,
                    "feature_as_of_date": _date(item.feature_as_of_date).isoformat(),
                    "feature_available_date": _date(item.feature_available_date).isoformat(),
                    "feature_values": list(item.feature_values),
                    "probability_transform_id": projection.probability_transform_id,
                    "probability_baseline_id": projection.probability_baseline_id,
                    "probability_baseline_kind": projection.probability_baseline_kind,
                    "probability_baseline_probability_bp": projection.probability_baseline_probability_bp,
                    "probability_lineage": [dict(node) for node in lineage],
                    "active_probability_bp": projection.calibrated_probability_bp,
                    "active_after_cost_probability_bp": projection.after_cost_profit_probability_bp,
                    "active_raw_probability_bp": projection.raw_calibrated_probability_bp,
                    "active_raw_after_cost_probability_bp": projection.raw_after_cost_profit_probability_bp,
                }
            )
        identity_hash = _hash_payload(identity)
        capture_identity: dict[str, Any] = {
            "active_identity_hash": identity_hash,
            "capture_as_of_date": capture_day,
            "rows": rows,
            "source_contract_binding": (
                dict(source_contract_binding) if source_contract_binding is not None else None
            ),
        }
        if resolved_scenario.is_estimated:
            capture_identity["cost_scenario_hash"] = resolved_scenario.scenario_hash
        capture_id = "active-capture-" + hashlib.sha256(
            json.dumps(capture_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        active_effective_date = str(
            consumer._loaded_pointer.get("effective_date")
            if getattr(consumer, "_loaded_pointer", None)
            else ""
        )[:10]
        schema_version = (
            "recommendation-active-model-prediction-capture.v2"
            if resolved_scenario.is_estimated
            else "recommendation-active-model-prediction-capture.v1"
        )
        contract_hash = recommendation_cost_contract_hash(
            resolved_scenario.fixed_round_trip_cost_bp,
            cost_scenario=resolved_scenario if resolved_scenario.is_estimated else None,
        )
        body: dict[str, Any] = {
            "schema_version": schema_version,
            "capture_id": capture_id,
            "capture_as_of_date": capture_day,
            "captured_at": captured_at,
            "active_identity": dict(identity),
            "active_identity_hash": identity_hash,
            "active_candidate_id": candidate_id,
            "active_model_id": model_id,
            "active_candidate_root": str(candidate_root),
            "active_candidate_frozen_at": candidate_frozen_at,
            "active_manifest_hash": str(identity.get("candidate_manifest_hash") or ""),
            "active_artifact_hash": str(identity.get("candidate_artifact_hash") or ""),
            "active_freeze_hash": str(identity.get("candidate_freeze_hash") or ""),
            "active_dataset_hash": identity.get("dataset_hash"),
            "active_pointer_version": int(identity.get("pointer_version", 0)),
            "active_effective_date": active_effective_date,
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash(feature_schema),
            "feature_schema": [list(item) for item in feature_schema],
            "label_registry_hash": expected_label_registry_hash,
            "cost_contract_hash": contract_hash,
            "fixed_round_trip_cost_bp": resolved_scenario.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": maximum_probability_change_bp,
            "policy_hash": policy_hash,
            "probability_transform_id": PROBABILITY_TRANSFORM_ID,
            "probability_lineage": [dict(item) for item in lineage],
            "rows": rows,
            "capture_origin": "scheduled_active_monitor",
        }
        resolved_source_contract_binding = (
            dict(source_contract_binding) if source_contract_binding is not None else None
        )
        if resolved_source_contract_binding is not None:
            resolved_source_contract_binding.update(
                {
                    "capture_decision_date": capture_day,
                    "capture_symbols": sorted({str(row["symbol"]) for row in rows}),
                    "feature_row_count": len(rows),
                    "feature_snapshot_fingerprint": _feature_snapshot_fingerprint(
                        capture_day,
                        rows,
                    ),
                }
            )
            _verify_source_contract_binding(
                resolved_source_contract_binding,
                require_ready=True,
                capture_day=_date(capture_day),
                capture_rows=rows,
                capture_at=captured_at,
                source_binding_verifier=source_binding_verifier,
            )
            body["source_contract_binding"] = resolved_source_contract_binding
        if resolved_scenario.is_estimated:
            # Hash the exact v3 fields that ``to_dict`` persists.  Using the
            # scenario's internal metadata shape here would emit
            # ``scenario_id``/``scenario_version`` while the durable capture
            # contract uses ``cost_scenario_id``/``cost_scenario_version``;
            # that would make an otherwise immutable capture fail its own
            # post-persist verification.
            body.update(_scenario_dataclass_kwargs(resolved_scenario))
        body["capture_hash"] = _hash_payload(body)
        return ActiveModelPredictionCapture(
            capture_id=capture_id,
            capture_as_of_date=capture_day,
            captured_at=captured_at,
            active_identity=dict(identity),
            active_identity_hash=identity_hash,
            active_candidate_id=candidate_id,
            active_model_id=model_id,
            active_candidate_root=str(candidate_root),
            active_candidate_frozen_at=candidate_frozen_at,
            active_manifest_hash=str(identity.get("candidate_manifest_hash") or ""),
            active_artifact_hash=str(identity.get("candidate_artifact_hash") or ""),
            active_freeze_hash=str(identity.get("candidate_freeze_hash") or ""),
            active_dataset_hash=(str(identity.get("dataset_hash")) if identity.get("dataset_hash") else None),
            active_pointer_version=int(identity.get("pointer_version", 0)),
            active_effective_date=active_effective_date,
            feature_registry_hash=feature_registry_hash,
            feature_schema_hash=feature_schema_hash(feature_schema),
            feature_schema=feature_schema,
            label_registry_hash=expected_label_registry_hash,
            cost_contract_hash=contract_hash,
            fixed_round_trip_cost_bp=resolved_scenario.fixed_round_trip_cost_bp,
            maximum_probability_change_bp=maximum_probability_change_bp,
            policy_hash=policy_hash,
            probability_transform_id=PROBABILITY_TRANSFORM_ID,
            probability_lineage=lineage,
            rows=tuple(rows),
            capture_hash=str(body["capture_hash"]),
            schema_version=schema_version,
            source_contract_binding=resolved_source_contract_binding,
            **(_scenario_dataclass_kwargs(resolved_scenario) if resolved_scenario.is_estimated else {}),
        )


@dataclass(frozen=True)
class MaturedRecommendationOutcome:
    capture_row_id: str
    label_end_date: str
    label_available_date: str
    stock_return_bp: int
    observed_liquidity_cost_bp: int | None
    benchmark_return_bp: int | None = None
    observed_liquidity_cost_source: str | None = None
    buy_price_twd: str | None = None
    sell_price_twd: str | None = None
    cost_scenario_id: str | None = None
    cost_scenario_version: str | None = None
    cost_scenario_hash: str | None = None
    cost_basis: str | None = None
    cost_policy_id: str | None = None
    cost_policy_version: str | None = None
    policy_estimate_date: str | None = None
    market_replay_date: str | None = None
    research_order_amount_twd: str | None = None
    research_order_quantity_shares: int | None = None
    lot_type: str | None = None
    instrument_type: str | None = None
    estimated_buy_cost_twd: str | None = None
    estimated_sell_cost_twd: str | None = None
    estimated_round_trip_cost_twd: str | None = None
    estimated_round_trip_cost_bp: int | None = None
    gross_buy_amount_twd: str | None = None
    gross_sell_amount_twd: str | None = None
    net_profit_twd: str | None = None
    cost_estimate_status: str | None = None
    cost_estimate_diagnostics: tuple[str, ...] = ()
    session_proof: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if _date(self.label_available_date) < _date(self.label_end_date):
            raise ValueError("label_available_date must not precede label_end_date")
        if self.observed_liquidity_cost_bp is not None and self.observed_liquidity_cost_bp < 0:
            raise ValueError("observed_liquidity_cost_bp must be non-negative")


@dataclass(frozen=True)
class NaturalEvidenceReceiptReference:
    receipt_path: str
    receipt_hash: str
    evidence_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "receipt_path": self.receipt_path,
            "receipt_hash": self.receipt_hash,
            "evidence_id": self.evidence_id,
        }


class RecommendationPredictionCaptureService:
    """Capture inference after candidate freeze and before future outcomes."""

    def capture(
        self,
        *,
        candidate_root: str | Path,
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        policy_hash: str,
        decision_date: str,
        captured_at: str,
        inputs: Sequence[RecommendationPredictionCaptureInput],
        fixed_round_trip_cost_bp: int | None,
        cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
        maximum_probability_change_bp: int = 1_000,
        data_root: str | Path | None = None,
        champion_pointer_path: str | Path | None = None,
        champion_inference: FrozenRecommendationInference | None = None,
        capture_origin: str = "scheduled_live",
        source_contract_binding: Mapping[str, Any] | None = None,
        source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    ) -> RecommendationPredictionCapture:
        candidate_path = Path(candidate_root).resolve()
        if capture_origin not in {"scheduled_live", "live_forward"}:
            raise ValueError("capture_origin must identify a live scheduled forward capture")
        if source_contract_binding is not None:
            _verify_source_contract_binding(
                source_contract_binding,
                require_ready=True,
                capture_at=captured_at,
                source_binding_verifier=source_binding_verifier,
            )
        if not 0 <= maximum_probability_change_bp <= 10_000:
            raise ValueError("maximum_probability_change_bp must be within 0..10000")
        candidate_payload = _read_json(candidate_path / "candidate.json")
        manifest_payload = _read_json(candidate_path / "manifest.json")
        candidate_id = str(candidate_payload.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("candidate identity is missing")
        try:
            declared_scenario = cost_scenario_from_metadata(
                candidate_payload,
                fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            )
            resolved_scenario = (
                declared_scenario
                if cost_scenario is None
                else normalize_cost_scenario(
                    cost_scenario,
                    fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
                )
            )
        except RecommendationCostScenarioError as exc:
            raise ValueError(str(exc)) from exc
        if resolved_scenario.is_estimated and fixed_round_trip_cost_bp is not None:
            raise ValueError("estimated capture must not carry fixed_round_trip_cost_bp")
        if (
            not resolved_scenario.is_estimated
            and fixed_round_trip_cost_bp is not None
            and resolved_scenario.fixed_round_trip_cost_bp != fixed_round_trip_cost_bp
        ):
            raise ValueError("capture fixed cost does not match cost scenario")
        if resolved_scenario.scenario_hash != declared_scenario.scenario_hash:
            raise ValueError("capture cost scenario does not match candidate")
        expected_label_registry_hash = str(
            candidate_payload.get("label_registry_hash") or ""
        )
        if not expected_label_registry_hash:
            raise ValueError("candidate label registry hash is missing")
        if candidate_payload.get("feature_schema_hash") != feature_schema_hash(feature_schema):
            raise ValueError("candidate feature schema hash mismatch")
        evaluation_payload = candidate_payload.get("evaluation")
        evaluation = evaluation_payload if isinstance(evaluation_payload, Mapping) else {}
        expected_freeze = candidate_freeze_hash(
            candidate_id=candidate_id,
            dataset_hash=str(candidate_payload.get("dataset_hash") or ""),
            manifest_hash=str(candidate_payload.get("manifest_hash") or ""),
            artifact_hash=str(candidate_payload.get("artifact_hash") or ""),
            evaluation=evaluation,
        )
        if candidate_payload.get("candidate_freeze_hash") != expected_freeze:
            raise ValueError("candidate freeze hash mismatch")
        if manifest_payload.get("manifest_hash") != candidate_payload.get("manifest_hash"):
            raise ValueError("candidate manifest identity mismatch")
        if manifest_payload.get("artifact_hash") != candidate_payload.get("artifact_hash"):
            raise ValueError("candidate artifact identity mismatch")
        if manifest_payload.get("feature_registry_hash") != feature_registry_hash:
            raise ValueError("candidate feature registry hash mismatch")
        if tuple(tuple(item) for item in manifest_payload.get("feature_schema", ())) != feature_schema:
            raise ValueError("candidate feature schema mismatch")
        if manifest_payload.get("production_action_allowed") is not False:
            raise ValueError("candidate must remain shadow-only")
        manifest_created_at = str(manifest_payload.get("created_at") or "")
        candidate_frozen_at = _datetime(manifest_created_at)
        captured_datetime = _datetime(captured_at)
        if candidate_frozen_at > captured_datetime:
            raise ValueError("candidate freeze must precede prediction capture")
        capture_day = _date(decision_date).isoformat()
        if _date(captured_at) > _date(decision_date):
            raise ValueError("prediction capture must not be after decision cutoff")
        if not inputs:
            raise ValueError("prediction capture requires at least one input row")
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=str(manifest_payload.get("model_family")),
            expected_feature_registry_hash=feature_registry_hash,
            expected_label_registry_hash=expected_label_registry_hash,
            expected_feature_schema=feature_schema,
            installed_library_versions=_library_versions(),
        )
        loaded = SafeShadowModelArtifactLoader(data_root=data_root).load(
            candidate_path,
            expectation=expectation,
        )
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            raise ValueError(f"candidate artifact is not loadable: {loaded.blockers}")
        if champion_pointer_path is not None and champion_inference is None:
            raise ValueError(
                "champion_inference must be injected when champion_pointer_path is provided"
            )
        champion_consumer = champion_inference
        champion_identity: Mapping[str, Any] | None = None
        if champion_consumer is not None:
            if champion_consumer.reload(decision_date=capture_day) != "active":
                champion_consumer = None
            else:
                champion_identity = champion_consumer.active_identity(decision_date=capture_day)
        baseline_id = (
            str(champion_identity.get("model_id") or "")
            if champion_identity is not None
            else str(inputs[0].rule_baseline_id)
        )
        baseline_kind = "active_model" if champion_identity is not None else (
            "null_benchmark"
            if baseline_id == NULL_BENCHMARK_BASELINE_ID
            else "declared_baseline"
        )
        if not baseline_id:
            raise ValueError("capture probability baseline identity is missing")
        transform = RecommendationProbabilityTransform(
            baseline_id=baseline_id,
            maximum_probability_change_bp=maximum_probability_change_bp,
        )
        champion_lineage = (
            tuple(dict(item) for item in champion_identity.get("probability_lineage", ()))
            if champion_identity is not None
            else ({
                "kind": "null_benchmark",
                "baseline_id": NULL_BENCHMARK_BASELINE_ID,
                "baseline_kind": "null_benchmark",
                "model_id": None,
                "candidate_id": None,
                "transform_id": PROBABILITY_TRANSFORM_ID,
                "maximum_probability_change_bp": maximum_probability_change_bp,
                "effective_prediction": "identity_from_explicit_baseline",
            },)
        )
        rows: list[Mapping[str, Any]] = []
        for item in sorted(inputs, key=lambda row: (row.row_id, row.symbol)):
            if _date(item.decision_date) != _date(decision_date):
                raise ValueError("all capture rows must use capture decision_date")
            prediction: RecommendationPrediction = loaded.model.predict(item.feature_values)
            champion_prediction = (
                champion_consumer.predict_active(
                    feature_values=item.feature_values,
                    decision_date=capture_day,
                    baseline_probability_bp=item.rule_probability_bp,
                    baseline_after_cost_probability_bp=item.rule_after_cost_probability_bp,
                )
                if champion_consumer is not None
                else None
            )
            champion_probability = (
                champion_prediction.calibrated_probability_bp
                if champion_prediction is not None
                else item.rule_probability_bp
            )
            champion_after_cost = (
                champion_prediction.after_cost_profit_probability_bp
                if champion_prediction is not None
                else item.rule_after_cost_probability_bp
            )
            if champion_probability is None:
                raise ValueError("active champion probability is unavailable")
            effective_probability = transform.apply(
                prediction.calibrated_probability_bp,
                champion_probability,
            )
            if effective_probability is None:
                raise ValueError("candidate probability is unavailable")
            effective_after_cost = (
                transform.apply(
                    prediction.after_cost_profit_probability_bp,
                    champion_after_cost,
                )
                if champion_after_cost is not None
                else None
            )
            rows.append(
                {
                    "row_id": item.row_id,
                    "symbol": item.symbol,
                    "decision_date": _date(item.decision_date).isoformat(),
                    "feature_as_of_date": _date(item.feature_as_of_date).isoformat(),
                    "feature_available_date": _date(item.feature_available_date).isoformat(),
                    "feature_values": list(item.feature_values),
                    "probability_transform_id": transform.transform_id,
                    "probability_baseline_id": baseline_id,
                    "probability_baseline_kind": baseline_kind,
                    "champion_probability_lineage": [dict(item) for item in champion_lineage],
                    "candidate_ranking_score_bp": prediction.ranking_score_bp,
                    # This is the final value consumed by the application. The
                    # raw model output remains separately auditable.
                    "candidate_model_probability_bp": prediction.calibrated_probability_bp,
                    "candidate_probability_bp": effective_probability,
                    "candidate_model_after_cost_probability_bp": prediction.after_cost_profit_probability_bp,
                    "candidate_after_cost_probability_bp": effective_after_cost,
                    "champion_model_probability_bp": (
                        champion_prediction.calibrated_probability_bp
                        if champion_prediction is not None
                        else None
                    ),
                    "champion_model_after_cost_probability_bp": (
                        champion_prediction.after_cost_profit_probability_bp
                        if champion_prediction is not None
                        else None
                    ),
                    "champion_probability_bp": champion_probability,
                    "champion_after_cost_probability_bp": champion_after_cost,
                }
            )
        resolved_source_contract_binding = (
            dict(source_contract_binding) if source_contract_binding is not None else None
        )
        if resolved_source_contract_binding is not None:
            resolved_source_contract_binding.update(
                {
                    "capture_decision_date": capture_day,
                    "capture_symbols": sorted({str(row["symbol"]) for row in rows}),
                    "feature_row_count": len(rows),
                    "feature_snapshot_fingerprint": _feature_snapshot_fingerprint(
                        capture_day,
                        rows,
                    ),
                }
            )
            _verify_source_contract_binding(
                resolved_source_contract_binding,
                require_ready=True,
                capture_day=_date(capture_day),
                capture_rows=rows,
                capture_at=captured_at,
                source_binding_verifier=source_binding_verifier,
            )
        schema_version = (
            "recommendation-prediction-capture.v3"
            if resolved_scenario.is_estimated
            else "recommendation-prediction-capture.v2"
        )
        capture_identity: dict[str, Any] = {
            "candidate_freeze_hash": candidate_payload["candidate_freeze_hash"],
            "capture_as_of_date": capture_day,
            "rows": rows,
            "source_contract_binding": resolved_source_contract_binding
            if resolved_source_contract_binding is not None
            else None,
        }
        if resolved_scenario.is_estimated:
            capture_identity["cost_scenario_hash"] = resolved_scenario.scenario_hash
        capture_id = "capture-" + hashlib.sha256(
            json.dumps(capture_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        label_hash = expected_label_registry_hash
        contract_hash = recommendation_cost_contract_hash(
            resolved_scenario.fixed_round_trip_cost_bp,
            cost_scenario=resolved_scenario if resolved_scenario.is_estimated else None,
        )
        body = {
            "schema_version": schema_version,
            "capture_id": capture_id,
            "capture_as_of_date": capture_day,
            "captured_at": captured_at,
            "candidate_id": candidate_id,
            "candidate_root": str(candidate_path),
            "candidate_freeze_hash": candidate_payload["candidate_freeze_hash"],
            "candidate_frozen_at": manifest_created_at,
            "candidate_manifest_hash": candidate_payload["manifest_hash"],
            "candidate_artifact_hash": candidate_payload["artifact_hash"],
            "dataset_hash": candidate_payload["dataset_hash"],
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash(feature_schema),
            "feature_schema": [list(item) for item in feature_schema],
            "label_registry_hash": label_hash,
            "cost_contract_hash": contract_hash,
            "fixed_round_trip_cost_bp": resolved_scenario.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": maximum_probability_change_bp,
            "policy_hash": policy_hash,
            "probability_transform_id": transform.transform_id,
            "probability_baseline_id": baseline_id,
            "probability_baseline_kind": baseline_kind,
            "probability_lineage": [dict(item) for item in champion_lineage],
            "champion_model_id": str(champion_identity.get("model_id") or "") if champion_identity else "",
            "champion_candidate_id": str(champion_identity.get("candidate_id") or "") if champion_identity else "",
            "champion_candidate_root": str(champion_identity.get("candidate_root") or "") if champion_identity else "",
            "champion_manifest_hash": str(champion_identity.get("candidate_manifest_hash") or "") if champion_identity else "",
            "champion_artifact_hash": str(champion_identity.get("candidate_artifact_hash") or "") if champion_identity else "",
            "champion_freeze_hash": str(champion_identity.get("candidate_freeze_hash") or "") if champion_identity else "",
            "champion_pointer_version": champion_identity.get("pointer_version") if champion_identity else None,
            "rows": rows,
            "capture_origin": capture_origin,
            "source_contract_binding": (
                resolved_source_contract_binding
                if resolved_source_contract_binding is not None
                else None
            ),
        }
        if resolved_scenario.is_estimated:
            # Hash the exact v3 fields that ``to_dict`` persists.  The
            # scenario metadata shape uses ``scenario_id``/``scenario_version``
            # while the durable capture contract uses the prefixed field
            # names, so hashing the former would make a persisted capture fail
            # its own verification.
            body.update(_scenario_dataclass_kwargs(resolved_scenario))
        capture_hash = _hash_payload(body)
        return RecommendationPredictionCapture(
            capture_id=capture_id,
            capture_as_of_date=capture_day,
            captured_at=captured_at,
            candidate_id=candidate_id,
            candidate_root=str(candidate_path),
            candidate_freeze_hash=str(candidate_payload["candidate_freeze_hash"]),
            candidate_frozen_at=manifest_created_at,
            candidate_manifest_hash=str(candidate_payload["manifest_hash"]),
            candidate_artifact_hash=str(candidate_payload["artifact_hash"]),
            dataset_hash=str(candidate_payload["dataset_hash"]),
            feature_registry_hash=feature_registry_hash,
            feature_schema_hash=feature_schema_hash(feature_schema),
            feature_schema=feature_schema,
            label_registry_hash=label_hash,
            cost_contract_hash=contract_hash,
            fixed_round_trip_cost_bp=resolved_scenario.fixed_round_trip_cost_bp,
            maximum_probability_change_bp=maximum_probability_change_bp,
            policy_hash=policy_hash,
            rows=tuple(rows),
            capture_hash=capture_hash,
            probability_transform_id=transform.transform_id,
            probability_baseline_id=baseline_id,
            probability_baseline_kind=baseline_kind,
            probability_lineage=tuple(dict(item) for item in champion_lineage),
            champion_model_id=str(champion_identity.get("model_id") or "") if champion_identity else "",
            champion_candidate_id=str(champion_identity.get("candidate_id") or "") if champion_identity else "",
            champion_candidate_root=str(champion_identity.get("candidate_root") or "") if champion_identity else "",
            champion_manifest_hash=str(champion_identity.get("candidate_manifest_hash") or "") if champion_identity else "",
            champion_artifact_hash=str(champion_identity.get("candidate_artifact_hash") or "") if champion_identity else "",
            champion_freeze_hash=str(champion_identity.get("candidate_freeze_hash") or "") if champion_identity else "",
            champion_pointer_version=(
                int(champion_identity["pointer_version"])
                if champion_identity and champion_identity.get("pointer_version") is not None
                else None
            ),
            capture_origin=capture_origin,
            source_contract_binding=(
                resolved_source_contract_binding
                if resolved_source_contract_binding is not None
                else None
            ),
            schema_version=schema_version,
            **(_scenario_dataclass_kwargs(resolved_scenario) if resolved_scenario.is_estimated else {}),
        )


class NaturalForwardEvidenceBuilder:
    """Read a capture plus matured outcomes and recompute all comparison metrics."""

    def build(
        self,
        *,
        capture: RecommendationPredictionCapture | str | Path,
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        output_path: str | Path,
        evaluation_at: datetime | None = None,
        source_id: str = "scheduled_forward_outcomes",
        source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    ) -> NaturalEvidenceReceiptReference:
        if isinstance(capture, RecommendationPredictionCapture) and capture.capture_path is None:
            # A capture must become a durable first-stage artifact before a
            # mature receipt can be built.  The automatic adjacent path keeps
            # the helper safe for callers while preserving the two-stage audit.
            capture.persist(Path(output_path).resolve().with_suffix(".capture.json"))
        capture_payload = _capture_payload(capture)
        _verify_capture_document(capture_payload, source_binding_verifier=source_binding_verifier)
        return self._build_from_payload(
            capture_payload=capture_payload,
            outcomes=outcomes,
            evaluation_date=evaluation_date,
            evaluation_at=evaluation_at,
            output_path=output_path,
            source_id=source_id,
        )

    def build_many(
        self,
        *,
        captures: Sequence[str | Path],
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        output_path: str | Path,
        evaluation_at: datetime | None = None,
        source_id: str = "scheduled_forward_outcomes",
        source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    ) -> NaturalEvidenceReceiptReference:
        """Build one receipt from multiple immutable daily captures.

        The bundle is only a durable index of source captures and copied
        prediction rows.  It never creates a prediction or a label; every
        source capture is re-hashed and re-verified before the aggregate is
        written.  This lets one frozen challenger accumulate a bounded
        cross-day natural cohort without evaluating a different candidate.
        """

        capture_paths = tuple(Path(item).resolve() for item in captures)
        if not capture_paths:
            raise ValueError("at least one prediction capture is required")
        payloads: list[dict[str, Any]] = []
        for path in capture_paths:
            payload = _read_json(path)
            _verify_capture_payload(payload, source_binding_verifier=source_binding_verifier)
            payload["capture_path"] = str(path)
            payloads.append(payload)
        bundle = _build_capture_bundle(payloads, capture_paths)
        bundle_path = Path(output_path).resolve().with_suffix(".capture-bundle.json")
        bundle["capture_path"] = str(bundle_path)
        _write_json_once(bundle_path, bundle)
        _verify_capture_bundle_payload(bundle, source_binding_verifier=source_binding_verifier)
        return self._build_from_payload(
            capture_payload=bundle,
            outcomes=outcomes,
            evaluation_date=evaluation_date,
            evaluation_at=evaluation_at,
            output_path=output_path,
            source_id=source_id,
        )

    def _build_from_payload(
        self,
        *,
        capture_payload: Mapping[str, Any],
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        evaluation_at: datetime | None,
        output_path: str | Path,
        source_id: str,
    ) -> NaturalEvidenceReceiptReference:
        evaluation_day = _date(evaluation_date)
        try:
            scenario = cost_scenario_from_metadata(
                capture_payload,
                fixed_round_trip_cost_bp=(
                    int(capture_payload["fixed_round_trip_cost_bp"])
                    if capture_payload.get("fixed_round_trip_cost_bp") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError(f"capture cost scenario is invalid: {exc}") from exc
        by_id = {str(row["row_id"]): row for row in capture_payload["rows"]}
        if len(by_id) != len(capture_payload["rows"]):
            raise ValueError("prediction capture row ids must be unique")
        outcome_ids = [row.capture_row_id for row in outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("matured outcomes must not duplicate capture row ids")
        outcome_by_id = {row.capture_row_id: row for row in outcomes}
        session_proofs: list[Mapping[str, Any]] = []
        comparisons: list[dict[str, Any]] = []
        for row_id, outcome in sorted(outcome_by_id.items()):
            capture_row = by_id.get(row_id)
            if capture_row is None:
                raise ValueError(f"outcome has no matching capture row: {row_id}")
            if _date(outcome.label_available_date) > evaluation_day:
                continue
            capture_day = _date(str(capture_row["decision_date"]))
            if evaluation_day < capture_day:
                raise ValueError("evaluation_date must follow prediction capture")
            if _date(outcome.label_end_date) <= capture_day:
                raise ValueError("matured label end must follow prediction capture")
            if not isinstance(outcome.session_proof, Mapping) or not outcome.session_proof:
                raise ValueError("matured outcome official session proof is missing")
            session_proof = dict(outcome.session_proof)
            for field_name in ("schema_version", "resolver_id", "resolver_version", "proof_hash"):
                if not str(session_proof.get(field_name) or ""):
                    raise ValueError("matured outcome official session proof is incomplete")
            session_proofs.append(session_proof)
            if capture_row.get("candidate_probability_bp") is None or capture_row.get("champion_probability_bp") is None:
                raise ValueError("capture probability missing")
            row_payload = {
                "capture_row_id": row_id,
                "symbol": capture_row["symbol"],
                "capture_as_of_date": capture_row["decision_date"],
                "feature_as_of_date": capture_row.get("feature_as_of_date"),
                "feature_available_date": capture_row.get("feature_available_date"),
                "feature_values": capture_row.get("feature_values"),
                "label_end_date": _date(outcome.label_end_date).isoformat(),
                "label_available_date": _date(outcome.label_available_date).isoformat(),
                "maturity_session_proof": session_proof,
                "stock_return_bp": outcome.stock_return_bp,
                "observed_liquidity_cost_bp": outcome.observed_liquidity_cost_bp,
                "observed_liquidity_cost_source": outcome.observed_liquidity_cost_source,
                "benchmark_return_bp": outcome.benchmark_return_bp,
                "probability_transform_id": capture_row.get("probability_transform_id"),
                "probability_baseline_id": capture_row.get("probability_baseline_id"),
                "probability_baseline_kind": capture_row.get("probability_baseline_kind"),
                "champion_probability_lineage": capture_row.get("champion_probability_lineage"),
                "candidate_model_probability_bp": capture_row.get("candidate_model_probability_bp"),
                "candidate_probability_bp": int(capture_row["candidate_probability_bp"]),
                "candidate_model_after_cost_probability_bp": capture_row.get("candidate_model_after_cost_probability_bp"),
                "champion_probability_bp": int(capture_row["champion_probability_bp"]),
                "candidate_after_cost_probability_bp": capture_row.get("candidate_after_cost_probability_bp"),
                "champion_after_cost_probability_bp": capture_row.get("champion_after_cost_probability_bp"),
            }
            row_payload["upside_label"] = int(outcome.stock_return_bp > 0)
            if scenario.is_estimated:
                row_payload.update(
                    {
                        "cost_scenario_id": outcome.cost_scenario_id or scenario.scenario_id,
                        "cost_scenario_version": outcome.cost_scenario_version or scenario.scenario_version,
                        "cost_scenario_hash": outcome.cost_scenario_hash or scenario.scenario_hash,
                        "cost_basis": outcome.cost_basis or scenario.cost_basis,
                        "cost_policy_id": outcome.cost_policy_id or scenario.policy_id,
                        "cost_policy_version": outcome.cost_policy_version or scenario.policy_version,
                        "policy_estimate_date": outcome.policy_estimate_date or scenario.policy_estimate_date,
                        "market_replay_date": outcome.market_replay_date or capture_row["decision_date"],
                        "research_order_amount_twd": outcome.research_order_amount_twd or (
                            str(scenario.research_order_amount_twd)
                            if scenario.research_order_amount_twd is not None
                            else None
                        ),
                        "research_order_quantity_shares": outcome.research_order_quantity_shares or scenario.research_order_quantity_shares,
                        "lot_type": outcome.lot_type or scenario.lot_type,
                        "instrument_type": outcome.instrument_type or scenario.instrument_type,
                        # These source-derived prices let promotion authority
                        # rerun the versioned policy instead of trusting the
                        # producer's serialized fee/tax amounts.
                        "buy_price_twd": outcome.buy_price_twd,
                        "sell_price_twd": outcome.sell_price_twd,
                        "estimated_buy_cost_twd": outcome.estimated_buy_cost_twd,
                        "estimated_sell_cost_twd": outcome.estimated_sell_cost_twd,
                        "estimated_round_trip_cost_twd": outcome.estimated_round_trip_cost_twd,
                        "estimated_round_trip_cost_bp": outcome.estimated_round_trip_cost_bp,
                        "gross_buy_amount_twd": outcome.gross_buy_amount_twd,
                        "gross_sell_amount_twd": outcome.gross_sell_amount_twd,
                        "net_profit_twd": outcome.net_profit_twd,
                        "cost_estimate_status": outcome.cost_estimate_status,
                        "cost_estimate_diagnostics": list(outcome.cost_estimate_diagnostics),
                    }
                )
                if row_payload["cost_scenario_hash"] != scenario.scenario_hash:
                    raise ValueError("matured outcome cost scenario mismatch")
                gross_buy = _decimal_or_none(outcome.gross_buy_amount_twd)
                gross_sell = _decimal_or_none(outcome.gross_sell_amount_twd)
                net_profit = _decimal_or_none(outcome.net_profit_twd)
                buy_cost = _decimal_or_none(outcome.estimated_buy_cost_twd)
                sell_cost = _decimal_or_none(outcome.estimated_sell_cost_twd)
                if (
                    outcome.cost_estimate_status == "estimated"
                    and gross_buy is not None
                    and gross_sell is not None
                    and net_profit is not None
                    and buy_cost is not None
                    and sell_cost is not None
                ):
                    expected_net = gross_sell - gross_buy - buy_cost - sell_cost
                    if expected_net != net_profit:
                        raise ValueError("matured outcome exact net profit mismatch")
                    row_payload["after_cost_profit_label"] = int(net_profit > 0)
                else:
                    # Missing policy/price/product inputs stay unavailable; an
                    # unavailable estimate is never interpreted as a loss.
                    row_payload["after_cost_profit_label"] = None
            else:
                if (
                    outcome.observed_liquidity_cost_bp is None
                    or outcome.observed_liquidity_cost_source is None
                ):
                    row_payload["after_cost_profit_label"] = None
                else:
                    row_payload["after_cost_profit_label"] = int(
                        outcome.stock_return_bp
                        > int(capture_payload["fixed_round_trip_cost_bp"]) + outcome.observed_liquidity_cost_bp
                    )
            comparisons.append(row_payload)
        if not comparisons:
            raise ValueError("no naturally matured outcome matches the prediction capture")
        candidate_probabilities = [int(row["candidate_probability_bp"]) for row in comparisons]
        champion_probabilities = [int(row["champion_probability_bp"]) for row in comparisons]
        labels = [int(row["upside_label"]) for row in comparisons]
        candidate_brier = _brier_bp(candidate_probabilities, labels)
        champion_brier = _brier_bp(champion_probabilities, labels)
        candidate_gap = _calibration_gap_bp(candidate_probabilities, labels)
        after_cost_rows = tuple(
            row
            for row in comparisons
            if row["after_cost_profit_label"] is not None
            and row["candidate_after_cost_probability_bp"] is not None
            and row["champion_after_cost_probability_bp"] is not None
        )
        if scenario.is_estimated:
            after_cost_status = (
                "estimated_fees_tax_only"
                if after_cost_rows
                else "estimated_cost_unavailable_or_baseline"
            )
        else:
            after_cost_status = "observed" if after_cost_rows else "missing_liquidity_or_baseline"
        after_cost_candidate_brier: int | None = None
        after_cost_champion_brier: int | None = None
        after_cost_improvement: int | None = None
        after_cost_gap: int | None = None
        after_cost_candidate_hash: str | None = None
        after_cost_champion_hash: str | None = None
        if after_cost_rows:
            after_candidate_probabilities = [int(row["candidate_after_cost_probability_bp"]) for row in after_cost_rows]
            after_champion_probabilities = [int(row["champion_after_cost_probability_bp"]) for row in after_cost_rows]
            after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
            after_cost_candidate_brier = _brier_bp(after_candidate_probabilities, after_labels)
            after_cost_champion_brier = _brier_bp(after_champion_probabilities, after_labels)
            after_cost_improvement = after_cost_champion_brier - after_cost_candidate_brier
            after_cost_gap = _calibration_gap_bp(after_candidate_probabilities, after_labels)
            after_cost_candidate_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_candidate_probabilities,
                }
            )
            after_cost_champion_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_champion_probabilities,
                }
            )
        fingerprint_rows = [
            {
                "capture_row_id": row["capture_row_id"],
                "label_end_date": row["label_end_date"],
                "label_available_date": row["label_available_date"],
                "stock_return_bp": row["stock_return_bp"],
                "observed_liquidity_cost_bp": row["observed_liquidity_cost_bp"],
                "observed_liquidity_cost_source": row.get("observed_liquidity_cost_source"),
            }
            for row in comparisons
        ]
        if scenario.is_estimated:
            fingerprint_rows = [
                {
                    **row,
                    "observed_liquidity_cost_bp": None,
                    "observed_liquidity_cost_source": None,
                }
                for row in fingerprint_rows
            ]
            for fingerprint_row, comparison in zip(fingerprint_rows, comparisons):
                fingerprint_row.update(
                    {
                        key: comparison.get(key)
                        for key in (
                            "cost_scenario_hash",
                            "policy_estimate_date",
                            "market_replay_date",
                            "buy_price_twd",
                            "sell_price_twd",
                            "estimated_buy_cost_twd",
                            "estimated_sell_cost_twd",
                            "estimated_round_trip_cost_twd",
                            "estimated_round_trip_cost_bp",
                            "gross_buy_amount_twd",
                            "gross_sell_amount_twd",
                            "net_profit_twd",
                            "cost_estimate_status",
                        )
                    }
                )
        comparison_fingerprint = _hash_payload(
            {"capture_id": capture_payload["capture_id"], "rows": fingerprint_rows}
        )
        candidate_prediction_hash = _hash_payload(
            {"row_ids": [row["capture_row_id"] for row in comparisons], "probabilities_bp": candidate_probabilities}
        )
        champion_prediction_hash = _hash_payload(
            {"row_ids": [row["capture_row_id"] for row in comparisons], "probabilities_bp": champion_probabilities}
        )
        evidence_id = "natural-evidence-" + hashlib.sha256(
            f"{capture_payload['capture_hash']}|{comparison_fingerprint}|{evaluation_day.isoformat()}".encode("utf-8")
        ).hexdigest()[:24]
        if evaluation_at is None:
            raise ValueError("natural evidence evaluation_at is required for session-bound receipts")
        if evaluation_at.tzinfo is None or evaluation_at.utcoffset() is None:
            raise ValueError("natural evidence evaluation_at must contain a timezone")
        normalized_evaluation_at = evaluation_at.astimezone(timezone.utc)
        if normalized_evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date() != evaluation_day:
            raise ValueError("natural evidence evaluation_at date does not match as_of_date")
        if normalized_evaluation_at > datetime.now(timezone.utc):
            raise ValueError("natural evidence evaluation_at cannot be future-dated")
        resolver_ids = {
            str(proof.get("resolver_id") or "") for proof in session_proofs
        }
        resolver_versions = {
            str(proof.get("resolver_version") or "") for proof in session_proofs
        }
        if len(resolver_ids) != 1 or len(resolver_versions) != 1:
            raise ValueError("natural evidence session resolver identity is inconsistent")
        body: dict[str, Any] = {
            "schema_version": (
                "recommendation-natural-forward-evidence.v3"
                if scenario.is_estimated
                else "recommendation-natural-forward-evidence.v2"
            ),
            "evidence_id": evidence_id,
            "source_id": source_id,
            "source_kind": "matured_forward_prediction_capture",
            "status": "matured",
            "as_of_date": evaluation_day.isoformat(),
            "evaluation_at": normalized_evaluation_at.isoformat(),
            "maturity_session_resolver_id": next(iter(resolver_ids)),
            "maturity_session_resolver_version": next(iter(resolver_versions)),
            "capture_id": capture_payload["capture_id"],
            "capture_hash": capture_payload["capture_hash"],
            "capture_as_of_date": capture_payload["capture_as_of_date"],
            "captured_at": capture_payload["captured_at"],
            "candidate_frozen_at": capture_payload["candidate_frozen_at"],
            "candidate_id": capture_payload["candidate_id"],
            "candidate_freeze_hash": capture_payload["candidate_freeze_hash"],
            "candidate_manifest_hash": capture_payload["candidate_manifest_hash"],
            "candidate_artifact_hash": capture_payload["candidate_artifact_hash"],
            "dataset_hash": capture_payload["dataset_hash"],
            "feature_registry_hash": capture_payload["feature_registry_hash"],
            "feature_schema_hash": capture_payload["feature_schema_hash"],
            "feature_schema": capture_payload["feature_schema"],
            "label_registry_hash": capture_payload["label_registry_hash"],
            "cost_contract_hash": capture_payload["cost_contract_hash"],
            "fixed_round_trip_cost_bp": capture_payload["fixed_round_trip_cost_bp"],
            "maximum_probability_change_bp": capture_payload["maximum_probability_change_bp"],
            "policy_hash": capture_payload["policy_hash"],
            "probability_transform_id": capture_payload.get("probability_transform_id", PROBABILITY_TRANSFORM_ID),
            "probability_baseline_id": capture_payload.get("probability_baseline_id"),
            "probability_baseline_kind": capture_payload.get("probability_baseline_kind"),
            "probability_lineage": capture_payload.get("probability_lineage"),
            "champion_model_id": capture_payload.get("champion_model_id"),
            "champion_candidate_id": capture_payload.get("champion_candidate_id"),
            "champion_candidate_root": capture_payload.get("champion_candidate_root"),
            "champion_manifest_hash": capture_payload.get("champion_manifest_hash"),
            "champion_artifact_hash": capture_payload.get("champion_artifact_hash"),
            "champion_freeze_hash": capture_payload.get("champion_freeze_hash"),
            "champion_pointer_version": capture_payload.get("champion_pointer_version"),
            "source_capture_ids": capture_payload.get("source_capture_ids", [capture_payload["capture_id"]]),
            "source_capture_hashes": capture_payload.get("source_capture_hashes", [capture_payload["capture_hash"]]),
            "source_capture_paths": capture_payload.get("source_capture_paths", [capture_payload.get("capture_path")]),
            "source_contract_bindings": capture_payload.get(
                "source_contract_bindings",
                [capture_payload.get("source_contract_binding")],
            ),
            "matured_sample_count": len(comparisons),
            "comparison_sample_fingerprint": comparison_fingerprint,
            "candidate_prediction_hash": candidate_prediction_hash,
            "champion_prediction_hash": champion_prediction_hash,
            "same_date_same_cost": True,
            "observed_champion_brier_bp": champion_brier,
            "observed_candidate_brier_bp": candidate_brier,
            "observed_brier_improvement_bp": champion_brier - candidate_brier,
            "observed_calibration_gap_bp": candidate_gap,
            "after_cost_evaluation_status": after_cost_status,
            "after_cost_matured_sample_count": len(after_cost_rows),
            "observed_champion_after_cost_brier_bp": after_cost_champion_brier,
            "observed_candidate_after_cost_brier_bp": after_cost_candidate_brier,
            "observed_after_cost_brier_improvement_bp": after_cost_improvement,
            "observed_after_cost_calibration_gap_bp": after_cost_gap,
            "after_cost_candidate_prediction_hash": after_cost_candidate_hash,
            "after_cost_champion_prediction_hash": after_cost_champion_hash,
            "capture_path": capture_payload.get("capture_path"),
            "capture_origin": capture_payload.get("capture_origin"),
            "comparisons": comparisons,
        }
        if scenario.is_estimated:
            body.update(_scenario_fields_from_mapping(capture_payload))
            body["cost_basis"] = scenario.cost_basis
            body["fixed_round_trip_cost_bp"] = None
            body["liquidity_cost_role"] = "diagnostic_only_not_in_fees_tax_only_label"
        body["receipt_body_hash"] = _hash_payload(body)
        destination = Path(output_path).resolve()
        _write_json_once(destination, body)
        return NaturalEvidenceReceiptReference(
            receipt_path=str(destination),
            receipt_hash=_sha256_file(destination),
            evidence_id=evidence_id,
        )


def _capture_payload(capture: RecommendationPredictionCapture | str | Path) -> dict[str, Any]:
    if isinstance(capture, RecommendationPredictionCapture):
        if capture.capture_path:
            return _read_json(Path(capture.capture_path).resolve())
        return capture.to_dict()
    return _read_json(Path(capture).resolve())


def _verify_capture_document(
    payload: Mapping[str, Any],
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> None:
    if payload.get("schema_version") == "recommendation-prediction-capture-bundle.v1":
        _verify_capture_bundle_payload(payload, source_binding_verifier=source_binding_verifier)
        return
    _verify_capture_payload(payload, source_binding_verifier=source_binding_verifier)


def verify_prediction_capture_read_only(
    capture: Mapping[str, Any] | str | Path,
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> RecommendationPredictionCaptureVerification:
    """Verify an immutable prediction capture without writing or maturing it.

    The implementation intentionally delegates all schema/hash/cost/source
    checks to the existing capture verifier.  This boundary only turns its
    successful result into a small typed read model for Workbench consumers.
    """

    if isinstance(capture, Mapping):
        payload = dict(capture)
    else:
        path = Path(capture).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("prediction capture must be an object")
    _verify_capture_document(payload, source_binding_verifier=source_binding_verifier)
    try:
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=(
                int(payload["fixed_round_trip_cost_bp"])
                if payload.get("fixed_round_trip_cost_bp") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        raise ValueError(f"prediction capture cost scenario is invalid: {exc}") from exc
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("prediction capture rows are missing")
    binding = payload.get("source_contract_binding")
    source_contract_status = (
        str(binding.get("price_up_prospective_status") or "unknown")
        if isinstance(binding, Mapping)
        else "not_supplied"
    )
    return RecommendationPredictionCaptureVerification(
        capture_id=str(payload["capture_id"]),
        candidate_id=str(payload["candidate_id"]),
        capture_as_of_date=_date(str(payload["capture_as_of_date"])).isoformat(),
        captured_at=str(payload["captured_at"]),
        capture_origin=str(payload["capture_origin"]),
        capture_hash=str(payload["capture_hash"]),
        row_count=len(rows),
        cost_basis=scenario.cost_basis,
        cost_scenario_id=scenario.scenario_id,
        cost_scenario_version=scenario.scenario_version,
        cost_scenario_hash=scenario.scenario_hash,
        fixed_round_trip_cost_bp=scenario.fixed_round_trip_cost_bp,
        source_contract_status=source_contract_status,
    )


def _build_capture_bundle(
    payloads: Sequence[Mapping[str, Any]],
    paths: Sequence[Path],
) -> dict[str, Any]:
    if not payloads or len(payloads) != len(paths):
        raise ValueError("capture bundle sources are missing")
    first = payloads[0]
    common_fields: tuple[str, ...] = (
        "candidate_id", "candidate_root", "candidate_freeze_hash",
        "candidate_frozen_at", "candidate_manifest_hash", "candidate_artifact_hash",
        "dataset_hash", "feature_registry_hash", "feature_schema_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
    )
    first_scenario = cost_scenario_from_metadata(
        first,
        fixed_round_trip_cost_bp=(
            int(first["fixed_round_trip_cost_bp"])
            if first.get("fixed_round_trip_cost_bp") is not None
            else None
        ),
    )
    if first_scenario.is_estimated:
        common_fields = common_fields + (
            "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
            "cost_basis", "cost_policy_id", "cost_policy_version",
            "policy_estimate_date", "research_order_amount_twd",
            "research_order_quantity_shares", "lot_type", "instrument_type",
            "cost_scenario",
        )
    for payload in payloads[1:]:
        for field_name in common_fields:
            if str(payload.get(field_name)) != str(first.get(field_name)):
                raise ValueError(f"capture bundle source mismatch: {field_name}")
    source_rows: list[Mapping[str, Any]] = []
    source_ids: list[str] = []
    source_hashes: list[str] = []
    source_paths: list[str] = []
    for payload, path in zip(payloads, paths):
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("capture bundle source rows are invalid")
        source_rows.extend(rows)
        source_ids.append(str(payload["capture_id"]))
        source_hashes.append(str(payload["capture_hash"]))
        source_paths.append(str(path.resolve()))
    row_ids = [str(row.get("row_id")) for row in source_rows if isinstance(row, Mapping)]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("capture bundle row ids must be unique")
    capture_days = sorted(_date(str(row["decision_date"])) for row in source_rows)
    if not capture_days:
        raise ValueError("capture bundle has no rows")
    bundle_id = "capture-bundle-" + hashlib.sha256(
        json.dumps(
            {"candidate_freeze_hash": first["candidate_freeze_hash"], "source_ids": source_ids},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    body: dict[str, Any] = {
        "schema_version": "recommendation-prediction-capture-bundle.v1",
        "capture_id": bundle_id,
        "capture_as_of_date": capture_days[0].isoformat(),
        "capture_as_of_date_max": capture_days[-1].isoformat(),
        "captured_at": min(str(payload["captured_at"]) for payload in payloads),
        "candidate_id": first["candidate_id"],
        "candidate_root": first["candidate_root"],
        "candidate_freeze_hash": first["candidate_freeze_hash"],
        "candidate_frozen_at": first["candidate_frozen_at"],
        "candidate_manifest_hash": first["candidate_manifest_hash"],
        "candidate_artifact_hash": first["candidate_artifact_hash"],
        "dataset_hash": first["dataset_hash"],
        "feature_registry_hash": first["feature_registry_hash"],
        "feature_schema_hash": first["feature_schema_hash"],
        "feature_schema": first.get("feature_schema", []),
        "label_registry_hash": first.get("label_registry_hash"),
        "cost_contract_hash": first["cost_contract_hash"],
        "fixed_round_trip_cost_bp": first["fixed_round_trip_cost_bp"],
        "maximum_probability_change_bp": first["maximum_probability_change_bp"],
        "policy_hash": first["policy_hash"],
        "probability_transform_id": first["probability_transform_id"],
        "probability_lineage": "per_capture_source",
        "probability_baseline_id": "per_capture_source",
        "probability_baseline_kind": "per_capture_source",
        "champion_model_id": "per_capture_source",
        "champion_candidate_id": "per_capture_source",
        "champion_candidate_root": "per_capture_source",
        "champion_manifest_hash": "per_capture_source",
        "champion_artifact_hash": "per_capture_source",
        "champion_freeze_hash": "per_capture_source",
        "champion_pointer_version": None,
        "source_capture_ids": source_ids,
        "source_capture_hashes": source_hashes,
        "source_capture_paths": source_paths,
        "source_contract_bindings": [
            payload.get("source_contract_binding") for payload in payloads
        ],
        "rows": source_rows,
        "capture_origin": "scheduled_live_bundle",
    }
    if first_scenario.is_estimated:
        body.update(_scenario_fields_from_mapping(first))
    body["capture_hash"] = _hash_payload(body)
    body["capture_path"] = None
    return body


def _verify_capture_bundle_payload(
    payload: Mapping[str, Any],
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> None:
    if payload.get("schema_version") != "recommendation-prediction-capture-bundle.v1":
        raise ValueError("capture bundle schema is unsupported")
    required = (
        "capture_id", "capture_as_of_date", "capture_as_of_date_max", "captured_at",
        "candidate_id", "candidate_root", "candidate_freeze_hash", "candidate_frozen_at",
        "candidate_manifest_hash", "candidate_artifact_hash", "dataset_hash",
        "feature_registry_hash", "feature_schema_hash", "cost_contract_hash",
        "fixed_round_trip_cost_bp", "maximum_probability_change_bp", "policy_hash",
        "probability_transform_id", "probability_lineage", "source_capture_ids", "source_capture_hashes",
        "source_capture_paths", "rows", "capture_hash", "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("capture bundle metadata is incomplete")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload["capture_hash"]:
        raise ValueError("capture bundle hash mismatch")
    if payload.get("probability_lineage") != "per_capture_source":
        raise ValueError("capture bundle probability lineage marker is invalid")
    source_ids_value = payload.get("source_capture_ids")
    source_hashes_value = payload.get("source_capture_hashes")
    source_paths_value = payload.get("source_capture_paths")
    if not (
        isinstance(source_ids_value, list)
        and isinstance(source_hashes_value, list)
        and isinstance(source_paths_value, list)
    ):
        raise ValueError("capture bundle source index is invalid")
    source_ids: list[Any] = source_ids_value
    source_hashes: list[Any] = source_hashes_value
    source_paths: list[Any] = source_paths_value
    if not source_ids or not (len(source_ids) == len(source_hashes) == len(source_paths)):
        raise ValueError("capture bundle source index is empty or misaligned")
    source_rows: list[Mapping[str, Any]] = []
    common_fields: tuple[str, ...] = (
        "candidate_id", "candidate_freeze_hash", "candidate_manifest_hash",
        "candidate_artifact_hash", "dataset_hash", "feature_registry_hash",
        "feature_schema_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
    )
    bundle_scenario = cost_scenario_from_metadata(
        payload,
        fixed_round_trip_cost_bp=(
            int(payload["fixed_round_trip_cost_bp"])
            if payload.get("fixed_round_trip_cost_bp") is not None
            else None
        ),
    )
    if bundle_scenario.is_estimated:
        common_fields = common_fields + (
            "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
            "cost_basis", "cost_policy_id", "cost_policy_version",
            "policy_estimate_date", "research_order_amount_twd",
            "research_order_quantity_shares", "lot_type", "instrument_type",
            "cost_scenario",
        )
    for source_id, source_hash, source_path in zip(source_ids, source_hashes, source_paths):
        path = Path(str(source_path)).resolve()
        source = _read_json(path)
        _verify_capture_payload(source, source_binding_verifier=source_binding_verifier)
        if str(source.get("capture_id")) != str(source_id) or str(source.get("capture_hash")) != str(source_hash):
            raise ValueError("capture bundle source hash or identity mismatch")
        for field_name in common_fields:
            if str(source.get(field_name)) != str(payload.get(field_name)):
                raise ValueError(f"capture bundle source binding mismatch: {field_name}")
        rows = source.get("rows")
        if not isinstance(rows, list):
            raise ValueError("capture bundle source rows are invalid")
        source_rows.extend(row for row in rows if isinstance(row, Mapping))
    rows = payload.get("rows")
    if not isinstance(rows, list) or rows != source_rows:
        raise ValueError("capture bundle rows do not match immutable sources")
    row_ids = [str(row.get("row_id")) for row in rows if isinstance(row, Mapping)]
    if len(row_ids) != len(rows) or len(row_ids) != len(set(row_ids)):
        raise ValueError("capture bundle row ids are invalid")
    capture_days = sorted(_date(str(row["decision_date"])) for row in rows if isinstance(row, Mapping))
    if not capture_days:
        raise ValueError("capture bundle has no rows")
    if payload.get("capture_as_of_date") != capture_days[0].isoformat() or payload.get("capture_as_of_date_max") != capture_days[-1].isoformat():
        raise ValueError("capture bundle date bounds mismatch")
    if payload.get("capture_origin") != "scheduled_live_bundle":
        raise ValueError("capture bundle origin is invalid")


def _verify_capture_payload(
    payload: Mapping[str, Any],
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> None:
    required = (
        "capture_id", "capture_as_of_date", "captured_at", "candidate_id",
        "candidate_freeze_hash", "candidate_frozen_at", "candidate_manifest_hash",
        "candidate_artifact_hash", "feature_registry_hash", "feature_schema_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp", "maximum_probability_change_bp",
        "policy_hash", "probability_transform_id", "probability_baseline_id",
        "probability_baseline_kind", "probability_lineage", "champion_model_id", "champion_candidate_id",
        "champion_candidate_root", "champion_manifest_hash", "champion_artifact_hash",
        "champion_freeze_hash", "champion_pointer_version", "rows", "capture_hash",
        "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("prediction capture metadata is incomplete")
    if payload.get("schema_version") not in {
        "recommendation-prediction-capture.v2",
        "recommendation-prediction-capture.v3",
    }:
        raise ValueError("prediction capture schema is unsupported")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload["capture_hash"]:
        raise ValueError("prediction capture hash mismatch")
    try:
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=(
                int(payload["fixed_round_trip_cost_bp"])
                if payload.get("fixed_round_trip_cost_bp") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        raise ValueError(f"prediction capture cost scenario is invalid: {exc}") from exc
    if payload.get("schema_version") == "recommendation-prediction-capture.v3" and not scenario.is_estimated:
        raise ValueError("prediction capture v3 must use estimated cost scenario")
    if payload.get("schema_version") == "recommendation-prediction-capture.v2" and scenario.is_estimated:
        raise ValueError("prediction capture v2 cannot use estimated cost scenario")
    expected_label_hash = recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )
    if payload.get("label_registry_hash") != expected_label_hash:
        raise ValueError("prediction capture label registry contract mismatch")
    expected_cost_hash = recommendation_cost_contract_hash(
        scenario.fixed_round_trip_cost_bp,
        cost_scenario=scenario if scenario.is_estimated else None,
    )
    if payload.get("cost_contract_hash") != expected_cost_hash:
        raise ValueError("prediction capture cost contract mismatch")
    if scenario.is_estimated and payload.get("fixed_round_trip_cost_bp") is not None:
        raise ValueError("estimated prediction capture cannot carry fixed cost")
    if _date(str(payload["captured_at"])) > _date(str(payload["capture_as_of_date"])):
        raise ValueError("prediction capture timestamp is after decision cutoff")
    if _datetime(str(payload["candidate_frozen_at"])) > _datetime(str(payload["captured_at"])):
        raise ValueError("candidate freeze is after prediction capture")
    if str(payload.get("capture_origin")) not in {"scheduled_live", "live_forward"}:
        raise ValueError("prediction capture origin is not a live forward capture")
    maximum_change = int(payload["maximum_probability_change_bp"])
    if not 0 <= maximum_change <= 10_000:
        raise ValueError("prediction capture probability cap is invalid")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("prediction capture rows are missing")
    baseline_id = str(payload.get("probability_baseline_id") or "")
    baseline_kind = str(payload.get("probability_baseline_kind") or "")
    if not baseline_id or baseline_kind not in {
        "active_model", "null_benchmark", "declared_baseline"
    }:
        raise ValueError("prediction capture baseline identity is invalid")
    if payload.get("probability_transform_id") != PROBABILITY_TRANSFORM_ID:
        raise ValueError("prediction capture probability transform is unsupported")
    if payload.get("source_contract_binding") is not None:
        _verify_source_contract_binding(
            payload["source_contract_binding"],
            require_ready=True,
            capture_at=str(payload["captured_at"]),
            source_binding_verifier=source_binding_verifier,
        )
    lineage = payload.get("probability_lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("prediction capture probability lineage is missing")
    if baseline_kind == "null_benchmark" and baseline_id != NULL_BENCHMARK_BASELINE_ID:
        raise ValueError("null benchmark baseline identity mismatch")
    if baseline_kind == "active_model" and not payload.get("champion_model_id"):
        raise ValueError("active champion model identity is missing")
    transform = RecommendationProbabilityTransform(
        baseline_id=baseline_id,
        maximum_probability_change_bp=maximum_change,
    )
    row_ids: set[str] = set()
    capture_day = _date(str(payload["capture_as_of_date"]))
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("prediction capture row is invalid")
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in row_ids:
            raise ValueError("prediction capture row ids must be unique")
        row_ids.add(row_id)
        if _date(str(row.get("decision_date"))) != capture_day:
            raise ValueError("prediction capture row decision date mismatch")
        if _date(str(row.get("feature_as_of_date"))) >= capture_day:
            raise ValueError("prediction capture feature is not point-in-time")
        if _date(str(row.get("feature_available_date"))) > capture_day:
            raise ValueError("prediction capture feature availability is after decision")
        for field_name in ("candidate_probability_bp", "champion_probability_bp"):
            _probability(int(row[field_name]), field_name)
        if row.get("probability_transform_id") != payload.get("probability_transform_id"):
            raise ValueError("prediction capture row probability transform mismatch")
        if row.get("probability_baseline_id") != payload.get("probability_baseline_id"):
            raise ValueError("prediction capture row probability baseline mismatch")
        if row.get("probability_baseline_kind") != payload.get("probability_baseline_kind"):
            raise ValueError("prediction capture row probability baseline kind mismatch")
        if row.get("champion_probability_lineage") != lineage:
            raise ValueError("prediction capture row probability lineage mismatch")
        raw_probability = row.get("candidate_model_probability_bp")
        if raw_probability is None or not isinstance(raw_probability, int):
            raise ValueError("prediction capture raw candidate probability is missing")
        _probability(raw_probability, "candidate_model_probability_bp")
        if int(row["candidate_probability_bp"]) != transform.apply(
            raw_probability,
            int(row["champion_probability_bp"]),
        ):
            raise ValueError("prediction capture candidate probability cap mismatch")
        raw_after_cost = row.get("candidate_model_after_cost_probability_bp")
        effective_after_cost = row.get("candidate_after_cost_probability_bp")
        if raw_after_cost is None:
            if effective_after_cost is not None:
                raise ValueError("prediction capture after-cost probability cap mismatch")
        else:
            if not isinstance(raw_after_cost, int):
                raise ValueError("prediction capture raw after-cost probability is invalid")
            _probability(raw_after_cost, "candidate_model_after_cost_probability_bp")
            champion_after_cost = row.get("champion_after_cost_probability_bp")
            if champion_after_cost is None or effective_after_cost != transform.apply(
                raw_after_cost,
                int(champion_after_cost),
            ):
                raise ValueError("prediction capture after-cost probability cap mismatch")
        champion_model_probability = row.get("champion_model_probability_bp")
        champion_model_after_cost = row.get("champion_model_after_cost_probability_bp")
        if baseline_kind == "active_model":
            if champion_model_probability != int(row["champion_probability_bp"]):
                raise ValueError("active champion probability identity mismatch")
            if champion_model_after_cost is not None and row.get("champion_after_cost_probability_bp") != champion_model_after_cost:
                raise ValueError("active champion after-cost probability identity mismatch")
        elif champion_model_probability is not None or champion_model_after_cost is not None:
            raise ValueError("null or declared baseline cannot carry active model prediction")
    if payload.get("source_contract_binding") is not None:
        _verify_source_contract_binding(
            payload["source_contract_binding"],
            require_ready=True,
            capture_day=capture_day,
            capture_rows=rows,
            capture_at=str(payload["captured_at"]),
            source_binding_verifier=source_binding_verifier,
        )


def _verify_source_contract_binding(
    binding: object,
    *,
    require_ready: bool,
    expected_contract_file_sha256: str | None = None,
    capture_day: date | None = None,
    capture_rows: Sequence[Mapping[str, Any]] | None = None,
    capture_at: str | None = None,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
) -> Mapping[str, Any]:
    """Verify a capture's immutable prospective-input source binding."""

    if (
        isinstance(binding, Mapping)
        and binding.get("schema_version") == "recommendation-calibration-capture-source-binding.v2"
    ):
        return _verify_current_observed_source_contract_binding(
            binding,
            require_ready=require_ready,
            expected_contract_file_sha256=expected_contract_file_sha256,
            capture_day=capture_day,
            capture_rows=capture_rows,
            capture_at=capture_at,
            source_binding_verifier=source_binding_verifier,
            read_session_resolver=read_session_resolver,
        )
    if read_session_resolver is not None:
        raise ValueError("pinned SQLite session is only supported for current-observed source bindings")
    if not isinstance(binding, Mapping):
        raise ValueError("capture source contract binding is invalid")
    if binding.get("schema_version") != "recommendation-calibration-capture-source-binding.v1":
        raise ValueError("capture source contract binding schema is unsupported")
    if binding.get("historical_pit_eligible") is not False:
        raise ValueError("capture source contract binding cannot claim historical PIT")
    if require_ready and binding.get("price_up_prospective_status") != "ready":
        raise ValueError("capture source contract prospective price-up source is not ready")
    contract_path = Path(str(binding.get("contract_path") or "")).expanduser().resolve()
    contract_file_hash = str(binding.get("contract_file_sha256") or "")
    contract_content_hash = str(binding.get("contract_content_sha256") or "")
    if not contract_path.is_file() or contract_path.is_symlink():
        raise ValueError("capture source contract receipt is missing")
    if not contract_file_hash.startswith("sha256:") or len(contract_file_hash) != 71:
        raise ValueError("capture source contract file hash is invalid")
    if _sha256_file(contract_path) != contract_file_hash:
        raise ValueError("capture source contract file hash mismatch")
    if expected_contract_file_sha256 is not None and contract_file_hash != expected_contract_file_sha256:
        raise ValueError("capture source contract has changed since capture")
    if not contract_content_hash.startswith("sha256:") or len(contract_content_hash) != 71:
        raise ValueError("capture source contract content hash is invalid")
    contract_payload = _read_json(contract_path)
    contract_body = {
        key: value
        for key, value in contract_payload.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    if contract_payload.get("contract_sha256") != _hash_payload(contract_body):
        raise ValueError("capture source contract self-hash mismatch")
    if contract_payload.get("contract_sha256") != contract_content_hash:
        raise ValueError("capture source contract content hash mismatch")
    if str(binding.get("decision_date") or "")[:10] != str(contract_payload.get("decision_date") or "")[:10]:
        raise ValueError("capture source contract decision identity mismatch")
    lanes = contract_payload.get("lanes")
    lanes = lanes if isinstance(lanes, Mapping) else {}
    price_up = lanes.get("price_up_calibration")
    price_up = price_up if isinstance(price_up, Mapping) else {}
    if price_up.get("prospective_status") != binding.get("price_up_prospective_status"):
        raise ValueError("capture source contract prospective status mismatch")
    if require_ready and price_up.get("prospective_status") != "ready":
        raise ValueError("capture source contract receipt is not ready")
    contract_symbols = {
        str(symbol).strip()
        for symbol in contract_payload.get("symbols", [])
        if str(symbol).strip()
    }
    binding_symbols = {
        str(symbol).strip()
        for symbol in binding.get("symbols", [])
        if str(symbol).strip()
    }
    if not contract_symbols or contract_symbols != binding_symbols:
        raise ValueError("capture source contract symbol identity mismatch")
    if capture_day is not None and str(binding.get("decision_date") or "")[:10] != capture_day.isoformat():
        raise ValueError("capture source contract decision cutoff mismatch")
    if capture_rows is not None:
        if capture_day is None:
            raise ValueError("capture source contract capture date is missing")
        capture_day_text = capture_day.isoformat()
        capture_symbols = {
            str(row.get("symbol") or "").strip()
            for row in capture_rows
            if str(row.get("symbol") or "").strip()
        }
        if capture_symbols != contract_symbols:
            raise ValueError("capture source contract does not cover capture symbols")
        if binding.get("capture_decision_date") != capture_day_text:
            raise ValueError("capture source contract capture date mismatch")
        if binding.get("capture_symbols") != sorted(capture_symbols):
            raise ValueError("capture source contract capture symbol fingerprint mismatch")
        if binding.get("feature_row_count") != len(capture_rows):
            raise ValueError("capture source contract feature row count mismatch")
        expected_fingerprint = _feature_snapshot_fingerprint(
            capture_day_text,
            capture_rows,
        )
        if binding.get("feature_snapshot_fingerprint") != expected_fingerprint:
            raise ValueError("capture source contract feature snapshot fingerprint mismatch")
        technical = contract_payload.get("technical")
        technical = technical if isinstance(technical, Mapping) else {}
        feature_snapshot = technical.get("prospective_feature_snapshot")
        if not isinstance(feature_snapshot, Mapping):
            raise ValueError("capture source contract feature snapshot missing")
        if not _verified_content_hash(feature_snapshot, "content_sha256"):
            raise ValueError("capture source contract feature snapshot hash mismatch")
        if binding.get("feature_snapshot_content_sha256") != feature_snapshot.get(
            "content_sha256"
        ):
            raise ValueError("capture source contract feature snapshot identity mismatch")
        expected_rows = feature_snapshot.get("rows")
        if not isinstance(expected_rows, list):
            raise ValueError("capture source contract feature snapshot rows missing")
        expected_by_symbol = {
            str(row.get("symbol") or ""): row
            for row in expected_rows
            if isinstance(row, Mapping) and str(row.get("symbol") or "")
        }
        actual_by_symbol = {
            str(row.get("symbol") or ""): row
            for row in capture_rows
            if str(row.get("symbol") or "")
        }
        if set(expected_by_symbol) != set(actual_by_symbol):
            raise ValueError("capture source contract feature symbol coverage mismatch")
        for symbol, actual in actual_by_symbol.items():
            expected = expected_by_symbol[symbol]
            for field_name in (
                "decision_date",
                "feature_as_of_date",
                "feature_available_date",
            ):
                if str(actual.get(field_name) or "")[:10] != str(expected.get(field_name) or "")[:10]:
                    raise ValueError(
                        "capture source contract feature timing/value identity mismatch"
                    )
            if list(actual.get("feature_values") or []) != list(
                expected.get("feature_values") or []
            ):
                raise ValueError("capture source contract feature values mismatch")
    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    feature_snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(feature_snapshot, Mapping):
        raise ValueError("capture source contract feature snapshot missing")
    if not _verified_content_hash(feature_snapshot, "content_sha256"):
        raise ValueError("capture source contract feature snapshot hash mismatch")
    if binding.get("feature_snapshot_content_sha256") != feature_snapshot.get(
        "content_sha256"
    ):
        raise ValueError("capture source contract feature snapshot identity mismatch")
    if capture_at is not None:
        _verify_source_availability(
            contract_payload,
            binding,
            capture_at=capture_at,
        )
    _verify_source_contract_dependencies(contract_payload, binding)
    return contract_payload


def _verify_current_observed_source_contract_binding(
    binding: Mapping[str, Any],
    *,
    require_ready: bool,
    expected_contract_file_sha256: str | None,
    capture_day: date | None,
    capture_rows: Sequence[Mapping[str, Any]] | None,
    capture_at: str | None,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
) -> Mapping[str, Any]:
    """Verify the separately-scoped current-observed research lane.

    This schema deliberately does not satisfy the historical prospective/PIT
    readiness gate. It verifies an exact G6 cycle, snapshot, source context,
    and current feature rows, then binds the captured inference to those rows.
    """

    if binding.get("binding_mode") != "current_observed":
        raise ValueError("current-observed source binding mode is invalid")
    if (
        binding.get("historical_pit_eligible") is not False
        or binding.get("formal_training_allowed") is not False
        or binding.get("current_restated") is not True
        or binding.get("research_only") is not True
    ):
        raise ValueError("current-observed source binding eligibility flags are invalid")
    contract_path = Path(str(binding.get("contract_path") or "")).expanduser().resolve()
    contract_file_hash = str(binding.get("contract_file_sha256") or "")
    contract_content_hash = str(binding.get("contract_content_sha256") or "")
    if not contract_path.is_file() or contract_path.is_symlink():
        raise ValueError("current-observed source contract receipt is missing")
    if not _is_sha256_digest(contract_file_hash) or _sha256_file(contract_path) != contract_file_hash:
        raise ValueError("current-observed source contract file hash mismatch")
    if expected_contract_file_sha256 is not None and contract_file_hash != expected_contract_file_sha256:
        raise ValueError("current-observed source contract has changed since capture")
    if not _is_sha256_digest(contract_content_hash):
        raise ValueError("current-observed source contract content hash is invalid")
    contract_payload = _read_json(contract_path)
    contract_body = {
        key: value
        for key, value in contract_payload.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    if _hash_payload(contract_body) != contract_content_hash:
        raise ValueError("current-observed source contract content hash mismatch")
    if contract_payload.get("contract_sha256") != contract_content_hash:
        raise ValueError("current-observed source contract self-hash mismatch")
    decision_text = str(contract_payload.get("decision_date") or "")[:10]
    if str(binding.get("decision_date") or "")[:10] != decision_text:
        raise ValueError("current-observed source contract decision identity mismatch")
    if capture_day is not None and decision_text != capture_day.isoformat():
        raise ValueError("current-observed source contract capture date mismatch")
    contract_symbols = _normalized_symbol_set(contract_payload.get("symbols"))
    binding_symbols = _normalized_symbol_set(binding.get("symbols"))
    if not contract_symbols or contract_symbols != binding_symbols:
        raise ValueError("current-observed source contract symbol identity mismatch")

    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    snapshot = technical.get("current_observed_feature_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("current-observed feature snapshot is missing")
    feature_snapshot_schema = snapshot.get("schema_version")
    if feature_snapshot_schema == "recommendation-current-observed-feature-snapshot.v1":
        if (
            snapshot.get("status") != "captured"
            or snapshot.get("verified") is not True
            or snapshot.get("current_restated") is not True
            or snapshot.get("historical_pit_eligible") is not False
            or snapshot.get("formal_training_allowed") is not False
            or snapshot.get("research_only") is not True
        ):
            raise ValueError("current-observed v1 feature snapshot flags or schema are invalid")
    elif feature_snapshot_schema == "recommendation-current-observed-feature-snapshot.v2":
        from ml_module.current_observed_feature_snapshot_composer import (
            verify_current_observed_feature_snapshot_v2,
        )

        try:
            verify_current_observed_feature_snapshot_v2(snapshot, source_binding_verifier=source_binding_verifier)
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            raise ValueError(f"current-observed v2 feature composition failed verification: {exc}") from exc
    else:
        raise ValueError("current-observed feature snapshot schema is unsupported")
    if not _verified_content_hash(snapshot, "content_sha256"):
        raise ValueError("current-observed feature snapshot content hash mismatch")
    if binding.get("current_observed_feature_snapshot_sha256") != snapshot.get("content_sha256"):
        raise ValueError("current-observed feature snapshot binding hash mismatch")
    if binding.get("feature_snapshot_content_sha256") != snapshot.get("content_sha256"):
        raise ValueError("current-observed feature snapshot identity mismatch")
    for field_name in (
        "cycle_id", "raw_run_id", "cycle_source_date", "discovery_status_path",
        "discovery_status_sha256", "cycle_terminal_path", "cycle_terminal_sha256",
        "discovery_raw_run_id", "discovery_cycle_terminal_path",
        "discovery_cycle_terminal_sha256", "discovery_cycle_terminal_status",
        "reuse_source_identity",
        "snapshot_database_path", "snapshot_database_sha256", "snapshot_receipt_path",
        "snapshot_receipt_sha256", "source_context_envelope_path",
        "source_context_envelope_sha256", "feature_as_of_date", "observed_at",
        "feature_registry_id", "feature_registry_hash", "feature_schema_hash",
        "rows_sha256", "row_count",
    ):
        if binding.get(field_name) != snapshot.get(field_name):
            raise ValueError(f"current-observed source binding identity mismatch: {field_name}")
    if not _is_sha256_digest(str(snapshot.get("rows_sha256") or "")):
        raise ValueError("current-observed feature rows hash is invalid")
    if feature_snapshot_schema == "recommendation-current-observed-feature-snapshot.v2":
        if (
            snapshot.get("scope_mode") != "verified_scheduled_snapshot_cohort"
            or binding.get("scope_mode") != "verified_scheduled_snapshot_cohort"
            or binding.get("composition_sha256") != snapshot.get("composition_sha256")
            or binding.get("cohort_hash") != snapshot.get("cohort_hash")
        ):
            raise ValueError("current-observed v2 scope/composition binding mismatch")
    rows = snapshot.get("rows")
    symbols = snapshot.get("symbols")
    if (
        not isinstance(rows, list)
        or not isinstance(symbols, list)
        or not rows
        or len(rows) != len(symbols)
        or snapshot.get("row_count") != len(rows)
        or _normalized_symbol_set(symbols) != contract_symbols
    ):
        raise ValueError("current-observed feature symbol coverage is incomplete")
    if _hash_payload({"rows": rows}) != snapshot.get("rows_sha256"):
        raise ValueError("current-observed feature rows hash mismatch")
    feature_ids = rows[0].get("feature_ids") if isinstance(rows[0], Mapping) else None
    if not isinstance(feature_ids, list) or len(feature_ids) != 20 or len(set(feature_ids)) != 20:
        raise ValueError("current-observed feature registry must contain exactly 20 slots")
    source_rows_hashes = snapshot.get("source_rows_sha256_by_table")
    batch_descriptors: list[Mapping[str, Any]] = []
    if feature_snapshot_schema == "recommendation-current-observed-feature-snapshot.v1":
        if not isinstance(source_rows_hashes, Mapping) or not source_rows_hashes:
            raise ValueError("current-observed source table fingerprints are missing")
        if any(not _is_sha256_digest(str(value)) for value in source_rows_hashes.values()):
            raise ValueError("current-observed source table fingerprint is invalid")
    else:
        if source_rows_hashes is not None:
            raise ValueError("current-observed v2 parent cannot claim global source-table hashes")
        composition = snapshot.get("batch_composition")
        raw_batches = composition.get("batches") if isinstance(composition, Mapping) else None
        if not isinstance(raw_batches, list) or not raw_batches:
            raise ValueError("current-observed v2 batch descriptors are missing")
        batch_descriptors = [item for item in raw_batches if isinstance(item, Mapping)]
        if len(batch_descriptors) != len(raw_batches):
            raise ValueError("current-observed v2 batch descriptor is not an object")
    entry_observation = snapshot.get("entry_observation")
    if not isinstance(entry_observation, Mapping):
        raise ValueError("current-observed entry observation is missing")
    if (
        entry_observation.get("schema_version")
        != "recommendation-current-observed-entry-observation.v1"
        or entry_observation.get("decision_date") != snapshot.get("decision_date")
        or entry_observation.get("cycle_source_date") != snapshot.get("cycle_source_date")
        or entry_observation.get("source_database_path") != snapshot.get("snapshot_database_path")
        or entry_observation.get("source_database_sha256") != snapshot.get("snapshot_database_sha256")
        or entry_observation.get("current_restated") is not True
        or entry_observation.get("research_only") is not True
        or entry_observation.get("historical_pit_eligible") is not False
        or entry_observation.get("formal_training_allowed") is not False
        or entry_observation.get("source_available_at") is not None
    ):
        raise ValueError("current-observed entry observation identity or flags are invalid")
    if entry_observation.get("status") == "captured":
        if read_session_resolver is None:
            _verify_current_observed_entry_observation(snapshot, entry_observation)
    elif entry_observation.get("status") not in {"pending", "blocked"}:
        raise ValueError("current-observed entry observation status is invalid")

    observed_text = str(snapshot.get("observed_at") or "")
    try:
        observed_clock = datetime.fromisoformat(observed_text.replace("Z", "+00:00"))
        if observed_clock.tzinfo is None or observed_clock.utcoffset() is None:
            raise ValueError("current-observed clock must be timezone-aware")
        observed_utc = observed_clock.astimezone(timezone.utc)
        snapshot_day = _date(str(snapshot.get("decision_date") or ""))
        feature_day = _date(str(snapshot.get("feature_as_of_date") or ""))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("current-observed snapshot clock or dates are invalid") from exc
    if snapshot_day.isoformat() != decision_text or feature_day >= snapshot_day:
        raise ValueError("current-observed feature date must precede its decision date")
    if require_ready and snapshot.get("status") != "captured":
        raise ValueError("current-observed research feature snapshot is not captured")

    # Preserve the exact discovery bytes because the raw runner's status path is
    # mutable. The child terminal and snapshot/context pins remain independently
    # immutable and are revalidated on every evidence read.
    encoded_status = snapshot.get("discovery_status_bytes_base64")
    if not isinstance(encoded_status, str):
        raise ValueError("current-observed raw discovery bytes are missing")
    try:
        status_bytes = base64.b64decode(encoded_status, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("current-observed raw discovery bytes are invalid") from exc
    status_sha = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
    if status_sha != snapshot.get("discovery_status_sha256"):
        raise ValueError("current-observed raw discovery bytes hash mismatch")
    try:
        discovery = json.loads(status_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current-observed raw discovery JSON is invalid") from exc
    if not isinstance(discovery, Mapping):
        raise ValueError("current-observed raw discovery root is invalid")
    child = discovery.get("current_stock_research_cycle")
    discovery_market_date = discovery.get("latest_core_date")
    discovery_run_id = snapshot.get("discovery_raw_run_id", snapshot.get("raw_run_id"))
    discovery_terminal_path = snapshot.get(
        "discovery_cycle_terminal_path", snapshot.get("cycle_terminal_path")
    )
    discovery_terminal_sha256 = snapshot.get(
        "discovery_cycle_terminal_sha256", snapshot.get("cycle_terminal_sha256")
    )
    discovery_child_status = snapshot.get("discovery_cycle_terminal_status", "completed")
    capacity_block_exception = (
        classify_current_observed_raw_status(discovery) == "blocked_insufficient_storage"
    )
    if (
        not _current_observed_raw_status_is_eligible(discovery)
        or discovery.get("run_id") != discovery_run_id
        or discovery_market_date != snapshot.get("cycle_source_date")
        or discovery.get("source_date") not in (None, discovery_market_date)
        or not isinstance(child, Mapping)
        or child.get("status") != discovery_child_status
        or child.get("raw_run_id") != discovery_run_id
        or child.get("terminal_receipt_path") != discovery_terminal_path
        or child.get("terminal_receipt_sha256") != discovery_terminal_sha256
        or child.get("source_date") != snapshot.get("cycle_source_date")
    ):
        raise ValueError("current-observed raw discovery identity mismatch")
    if discovery_child_status == "completed":
        if (
            discovery_run_id != snapshot.get("raw_run_id")
            or discovery_terminal_path != snapshot.get("cycle_terminal_path")
            or discovery_terminal_sha256 != snapshot.get("cycle_terminal_sha256")
            or snapshot.get("cycle_id") != snapshot.get("raw_run_id")
            or snapshot.get("reuse_source_identity") not in (None, {})
        ):
            raise ValueError("current-observed completed discovery/source identities differ")
    elif discovery_child_status == "skipped_same_inputs":
        reuse_identity = verify_current_observed_cycle_reuse(
            reuse_terminal_path=str(discovery_terminal_path or ""),
            reuse_terminal_sha256=str(discovery_terminal_sha256 or ""),
            expected_raw_run_id=str(discovery_run_id or ""),
            expected_source_date=str(snapshot.get("cycle_source_date") or ""),
            require_original_capacity=capacity_block_exception,
            formal_output_root=(
                str(discovery.get("output_root") or "")
                if capacity_block_exception
                else None
            ),
        )
        if (
            snapshot.get("reuse_source_identity") != dict(reuse_identity)
            or snapshot.get("cycle_id") != reuse_identity.get("original_cycle_id")
            or snapshot.get("raw_run_id") != reuse_identity.get("original_raw_run_id")
            or snapshot.get("cycle_terminal_path") != reuse_identity.get("original_terminal_path")
            or snapshot.get("cycle_terminal_sha256") != reuse_identity.get("original_terminal_sha256")
        ):
            raise ValueError("current-observed reuse/source cycle identities differ")
    else:
        raise ValueError("current-observed discovery child status is unsupported")

    repository_root = Path(__file__).resolve().parents[1]
    research_roots = _current_observed_research_roots()
    requested_terminal_path = Path(str(snapshot.get("cycle_terminal_path") or ""))
    if not requested_terminal_path.is_absolute():
        raise ValueError("current-observed cycle terminal path is not absolute")
    try:
        validated_terminal_path = resolve_ml_research_output_path(
            requested_terminal_path,
            repository_root=repository_root,
            access="read",
        )
        terminal_path = validated_terminal_path.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("current-observed cycle terminal path is outside research roots") from exc
    if (
        terminal_path != validated_terminal_path
        or not terminal_path.is_file()
        or not _is_below_current_observed_cycle_root(terminal_path, research_roots)
    ):
        raise ValueError("current-observed cycle terminal path is outside the research root")
    terminal_bytes = terminal_path.read_bytes()
    terminal_sha = "sha256:" + hashlib.sha256(terminal_bytes).hexdigest()
    if terminal_sha != snapshot.get("cycle_terminal_sha256"):
        raise ValueError("current-observed cycle terminal hash mismatch")
    try:
        terminal = json.loads(terminal_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current-observed cycle terminal JSON is invalid") from exc
    pins = terminal.get("same_run_pins") if isinstance(terminal, Mapping) else None
    if (
        not isinstance(terminal, Mapping)
        or terminal.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or terminal.get("status") != "completed"
        or terminal.get("cycle_id") != snapshot.get("cycle_id")
        or terminal.get("raw_run_id") != snapshot.get("raw_run_id")
        or terminal.get("source_date") != snapshot.get("cycle_source_date")
        or not isinstance(pins, Mapping)
    ):
        raise ValueError("current-observed cycle terminal identity mismatch")
    if capacity_block_exception and discovery_child_status == "completed":
        terminal_research_root = _current_observed_research_root_for_path(
            terminal_path, research_roots
        )
        if not current_stock_research_capacity_passed(
            terminal,
            expected_raw_run_id=str(discovery_run_id or ""),
            expected_source_date=str(snapshot.get("cycle_source_date") or ""),
            formal_output_root=str(discovery.get("output_root") or ""),
            expected_research_root=terminal_research_root or "",
        ):
            raise ValueError(
                "current-observed G6 terminal capacity proof is invalid under formal bootstrap block"
            )
    for snapshot_key, terminal_key in (
        ("snapshot_database_path", "snapshot_database_path"),
        ("snapshot_database_sha256", "snapshot_database_sha256"),
        ("snapshot_receipt_path", "snapshot_receipt_path"),
        ("snapshot_receipt_sha256", "snapshot_receipt_sha256"),
        ("source_context_envelope_path", "source_context_envelope_path"),
        ("source_context_envelope_sha256", "source_context_envelope_sha256"),
    ):
        if snapshot_key.endswith("_sha256"):
            snapshot_digest = _normalized_sha256_hex(snapshot.get(snapshot_key))
            terminal_digest = _normalized_sha256_hex(pins.get(terminal_key))
            if snapshot_digest is None or snapshot_digest != terminal_digest:
                raise ValueError(f"current-observed terminal pin mismatch: {snapshot_key}")
        elif snapshot.get(snapshot_key) != pins.get(terminal_key):
            raise ValueError(f"current-observed terminal pin mismatch: {snapshot_key}")
    snapshot_database_sha256 = snapshot.get("snapshot_database_sha256")
    if type(snapshot_database_sha256) is not str or not _is_sha256_digest(snapshot_database_sha256):
        raise ValueError("current-observed snapshot database hash is invalid")

    try:
        from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
        from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
        from ml_module.historical_feature_builder import HistoricalFeatureBuilder

        context = load_current_observed_context_from_pinned_snapshot(
            snapshot,
            read_session_resolver=read_session_resolver,
        )
        if (
            Path(str(context.snapshot_database_path)).resolve()
            != Path(str(snapshot["snapshot_database_path"])).resolve()
            or _normalized_sha256_hex(context.snapshot_database_sha256)
            != _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
            or Path(str(context.snapshot_receipt_path)).resolve()
            != Path(str(snapshot["snapshot_receipt_path"])).resolve()
            or _normalized_sha256_hex(context.snapshot_receipt_sha256)
            != _normalized_sha256_hex(snapshot.get("snapshot_receipt_sha256"))
        ):
            raise ValueError("current-observed source context pins mismatch")
        read_session = (
            _current_observed_read_session(snapshot, read_session_resolver)
            if read_session_resolver is not None
            else None
        )
        if entry_observation.get("status") == "captured" and read_session is not None:
            _verify_current_observed_entry_observation(
                snapshot,
                entry_observation,
                read_session=read_session,
            )
        expected_rows = {str(row.get("symbol")): row for row in rows if isinstance(row, Mapping)}
        if set(expected_rows) != set(contract_symbols):
            raise ValueError("current-observed feature rows have incomplete symbol coverage")
        replay_batches: list[tuple[tuple[str, ...], Mapping[str, Any] | None]]
        if feature_snapshot_schema == "recommendation-current-observed-feature-snapshot.v1":
            replay_batches = [(tuple(str(symbol) for symbol in symbols), source_rows_hashes)]
        else:
            replay_batches = [
                (
                    tuple(str(symbol) for symbol in descriptor.get("symbols", ())),
                    descriptor.get("source_rows_sha256_by_table")
                    if isinstance(descriptor.get("source_rows_sha256_by_table"), Mapping)
                    else None,
                )
                for descriptor in batch_descriptors
            ]
        for batch_symbols, expected_table_hashes in replay_batches:
            if not 1 <= len(batch_symbols) <= 16 or expected_table_hashes is None:
                raise ValueError("current-observed feature replay batch is outside the bounded contract")
            raw_snapshot = MLHistoricalSnapshotProvider(Path(str(snapshot["snapshot_database_path"]))).load_current_observed(
                decision_date=decision_text,
                history_start_date=str(snapshot.get("history_start_date") or ""),
                symbols=batch_symbols,
                source_context=context,
                local_current_observed_at=observed_clock,
                expected_feature_as_of_date=feature_day.isoformat(),
                cycle_id=str(snapshot["cycle_id"]),
                cycle_terminal_path=terminal_path,
                cycle_terminal_sha256=terminal_sha,
                source_context_envelope_path=str(snapshot["source_context_envelope_path"]),
                source_context_envelope_sha256=(
                    "sha256:"
                    + str(_normalized_sha256_hex(snapshot.get("source_context_envelope_sha256")))
                ),
                read_session=read_session,
            )
            actual_table_hashes = dict(raw_snapshot.source_rows_sha256_by_table)
            _require_same_source_row_hashes(expected_table_hashes, actual_table_hashes)
            computed_rows = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY).compute_current_observed(
                raw_snapshot,
                industry_index_name_by_symbol={},
            )
            if tuple(str(row.symbol) for row in computed_rows) != batch_symbols:
                raise ValueError("current-observed feature recomputation symbol mismatch")
            for computed in computed_rows:
                row = expected_rows[computed.symbol]
                exact_values = [value for _, value in computed.values]
                if (
                    row.get("decision_date") != computed.decision_date
                    or row.get("feature_as_of_date") != computed.feature_as_of_date
                    or row.get("feature_available_date") != computed.decision_date
                    or row.get("local_current_observed_at") != computed.local_current_observed_at.isoformat()
                    or row.get("feature_registry_id") != computed.feature_registry_id
                    or row.get("feature_registry_hash") != computed.feature_registry_hash
                    or row.get("feature_schema_hash") != computed.feature_schema_hash
                    or row.get("feature_ids") != list(computed.feature_ids)
                    or row.get("feature_values") != exact_values
                    or row.get("missing_feature_ids") != list(computed.missing_feature_ids)
                    or row.get("source_row_sha256_by_table")
                    != [list(item) for item in computed.source_row_sha256_by_table]
                    or row.get("row_sha256") != computed.row_sha256
                ):
                    raise ValueError("current-observed feature rows changed since capture")
    except InterruptedError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        raise ValueError(f"current-observed snapshot revalidation failed: {exc}") from exc

    if capture_at is not None:
        try:
            capture_clock = datetime.fromisoformat(str(capture_at).replace("Z", "+00:00"))
            if capture_clock.tzinfo is None or capture_clock.utcoffset() is None:
                raise ValueError("capture clock must be timezone-aware")
            if capture_clock.astimezone(timezone.utc) < observed_utc:
                raise ValueError("capture predates current-observed feature snapshot")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("current-observed capture timestamp is invalid") from exc
    if capture_rows is not None:
        actual_by_symbol = {
            str(row.get("symbol") or ""): row
            for row in capture_rows
            if isinstance(row, Mapping) and str(row.get("symbol") or "")
        }
        expected_by_symbol = {
            str(row.get("symbol") or ""): row for row in rows if isinstance(row, Mapping)
        }
        if set(actual_by_symbol) != contract_symbols or set(expected_by_symbol) != contract_symbols:
            raise ValueError("current-observed capture symbol coverage mismatch")
        for symbol, actual in actual_by_symbol.items():
            expected = expected_by_symbol[symbol]
            if (
                str(actual.get("decision_date") or "")[:10] != decision_text
                or str(actual.get("feature_as_of_date") or "")[:10]
                != str(expected.get("feature_as_of_date") or "")[:10]
                or str(actual.get("feature_available_date") or "")[:10] != decision_text
                or actual.get("feature_values") != expected.get("feature_values")
                or actual.get("source_row_sha256_by_table")
                != expected.get("source_row_sha256_by_table")
            ):
                raise ValueError(
                    "current-observed capture row differs from frozen feature values or source lineage"
                )
    return contract_payload


def verify_current_observed_input_capture(
    source: Mapping[str, Any] | str | Path,
    *,
    expected_sha256: str | None = None,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
    read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
) -> Mapping[str, Any]:
    """Verify a no-model current-observed feature/entry capture.

    This research bootstrap contains no candidate identity or probability. It
    is independently source-bound and can only supply mature current-observed
    outcomes to a shadow research fit; it never changes historical PIT gates.
    """

    capture_path: Path | None = None
    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        capture_path = Path(source).expanduser().resolve(strict=True)
        if capture_path.is_symlink() or not capture_path.is_file() or capture_path.suffix != ".json":
            raise ValueError("current-observed input capture path is invalid")
        if "current_observed_captures" not in capture_path.parts:
            raise ValueError("current-observed input capture is outside its immutable store")
        actual_sha256 = _sha256_file(capture_path)
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise ValueError("current-observed input capture file hash mismatch")
        payload = _read_json(capture_path)
        payload["_verified_capture_path"] = str(capture_path)
        payload["_verified_capture_sha256"] = actual_sha256

    capture_schema = payload.get("schema_version")
    if capture_schema not in {
        "recommendation-current-observed-input-capture.v1",
        "recommendation-current-observed-input-capture.v2",
    }:
        raise ValueError("current-observed input capture schema is invalid")
    if (
        payload.get("status") != "captured"
        or payload.get("current_restated") is not True
        or payload.get("research_only") is not True
        or payload.get("historical_pit_eligible") is not False
        or payload.get("formal_training_allowed") is not False
        or payload.get("natural_outcome_only") is not True
    ):
        raise ValueError("current-observed input capture eligibility flags are invalid")
    forbidden_fields = {
        "probability", "probability_bp", "predicted_probability_bp", "predictions",
        "model_id", "candidate_id", "active_identity_hash", "active_model_identity",
    }
    if forbidden_fields.intersection(payload):
        raise ValueError("no-model current-observed capture contains model output fields")
    declared_content_hash = payload.get("content_sha256")
    if not _is_sha256_digest(str(declared_content_hash or "")):
        raise ValueError("current-observed input capture content hash is invalid")
    canonical_body = {
        key: value
        for key, value in payload.items()
        if key not in {"content_sha256", "capture_id", "_verified_capture_path", "_verified_capture_sha256"}
    }
    if _hash_payload(canonical_body) != declared_content_hash:
        raise ValueError("current-observed input capture content hash mismatch")
    decision_text = str(payload.get("decision_date") or "")[:10]
    cycle_id = str(payload.get("cycle_id") or "")
    expected_capture_id = f"current-observed:{decision_text}:{cycle_id}:{str(declared_content_hash)[7:]}"
    if not cycle_id or payload.get("capture_id") != expected_capture_id:
        raise ValueError("current-observed input capture ID mismatch")
    try:
        capture_clock = datetime.fromisoformat(str(payload.get("captured_at") or "").replace("Z", "+00:00"))
        decision_day = _date(decision_text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("current-observed input capture date/clock is invalid") from exc
    if (
        capture_clock.tzinfo is None
        or capture_clock.utcoffset() is None
        or capture_clock.astimezone(ZoneInfo("Asia/Taipei")).date() != decision_day
    ):
        raise ValueError("current-observed input capture clock is not a same-day Taipei observation")
    binding = payload.get("source_contract_binding")
    rows = payload.get("rows")
    if not isinstance(binding, Mapping) or not isinstance(rows, list) or not rows:
        raise ValueError("current-observed input capture source binding or rows are missing")
    _verify_source_contract_binding(
        binding,
        require_ready=True,
        capture_day=decision_day,
        capture_rows=rows,
        capture_at=str(payload.get("captured_at")),
        source_binding_verifier=source_binding_verifier,
        read_session_resolver=read_session_resolver,
    )
    snapshot = binding.get("current_observed_feature_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("current-observed input capture feature snapshot is missing")
    if (
        capture_schema == "recommendation-current-observed-input-capture.v1"
        and snapshot.get("schema_version") != "recommendation-current-observed-feature-snapshot.v1"
    ) or (
        capture_schema == "recommendation-current-observed-input-capture.v2"
        and snapshot.get("schema_version") != "recommendation-current-observed-feature-snapshot.v2"
    ):
        raise ValueError("current-observed input capture and feature snapshot versions differ")
    if capture_schema == "recommendation-current-observed-input-capture.v2" and (
        payload.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or binding.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or snapshot.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or payload.get("composition_sha256") != snapshot.get("composition_sha256")
        or binding.get("composition_sha256") != snapshot.get("composition_sha256")
    ):
        raise ValueError("current-observed v2 capture cohort/composition identity mismatch")
    entry_observation = snapshot.get("entry_observation")
    if not isinstance(entry_observation, Mapping) or entry_observation.get("status") != "captured":
        raise ValueError("current-observed input capture lacks exact same-date entry prices")
    entry_by_symbol = payload.get("entry_price_pin_by_symbol")
    benchmark_pin = payload.get("benchmark_entry_price_pin")
    expected_entry_by_symbol = entry_observation.get("entry_price_pin_by_symbol")
    expected_benchmark_pin = entry_observation.get("benchmark_entry_price_pin")
    if (
        not isinstance(entry_by_symbol, Mapping)
        or not isinstance(expected_entry_by_symbol, Mapping)
        or dict(entry_by_symbol) != dict(expected_entry_by_symbol)
        or not isinstance(benchmark_pin, Mapping)
        or not isinstance(expected_benchmark_pin, Mapping)
        or dict(benchmark_pin) != dict(expected_benchmark_pin)
    ):
        raise ValueError("current-observed input capture entry price pins differ from source snapshot")
    scenario_payload = payload.get("cost_scenario")
    fixed_cost_value = payload.get("fixed_round_trip_cost_bp")
    if not isinstance(scenario_payload, Mapping):
        raise ValueError("current-observed input capture cost scenario metadata is missing")
    if fixed_cost_value is not None and type(fixed_cost_value) is not int:
        raise ValueError("current-observed fixed cost must be an integer or null")
    expected_scenario = cost_scenario_from_metadata(
        scenario_payload,
        fixed_round_trip_cost_bp=fixed_cost_value,
    )
    if (
        payload.get("cost_status") != "verified"
        or payload.get("cost_scenario_id") != expected_scenario.scenario_id
        or payload.get("cost_scenario_version") != expected_scenario.scenario_version
        or payload.get("cost_scenario_hash") != expected_scenario.scenario_hash
        or payload.get("cost_scenario_basis") != expected_scenario.cost_basis
        or payload.get("cost_basis") != expected_scenario.cost_basis
        or payload.get("cost_contract_hash")
        != recommendation_cost_contract_hash(
            expected_scenario.fixed_round_trip_cost_bp,
            cost_scenario=expected_scenario if expected_scenario.is_estimated else None,
        )
        or payload.get("label_registry_hash")
        != recommendation_label_registry_hash(
            cost_scenario=expected_scenario if expected_scenario.is_estimated else None,
        )
    ):
        raise ValueError("current-observed input capture cost contract is invalid")
    return payload


def _current_observed_raw_status_is_eligible(payload: Mapping[str, Any]) -> bool:
    """分類完成、正式 revision block或窄容量例外的 raw status。"""

    return classify_current_observed_raw_status(payload) != "ineligible"


_CURRENT_SOURCE_SHARED_MEMORY_FIELDS = frozenset(
    {"shared_memory_before", "shared_memory_after"}
)
_CURRENT_SOURCE_FILE_PIN_FIELDS = frozenset({"path", "bytes", "mtime_ns", "sha256"})


def _exact_current_source_json_identity(left: object, right: object) -> bool:
    """Compare source observation JSON with exact value types and structure."""
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            return False
        if left.keys() != right.keys():
            return False
        return all(_exact_current_source_json_identity(left[key], right[key]) for key in left)
    if isinstance(left, list) or isinstance(right, list):
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            return False
        return all(_exact_current_source_json_identity(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _same_current_source_file_observation(
    left: object,
    right: object,
) -> bool:
    """Compare one SHM observation, ignoring only its between-capture mtime."""
    if left is None or right is None:
        return left is None and right is None
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if left.keys() != _CURRENT_SOURCE_FILE_PIN_FIELDS or right.keys() != _CURRENT_SOURCE_FILE_PIN_FIELDS:
        return False

    for pin in (left, right):
        path = pin.get("path")
        byte_count = pin.get("bytes")
        mtime_ns = pin.get("mtime_ns")
        digest = pin.get("sha256")
        if (
            type(path) is not str
            or not path.strip()
            or type(byte_count) is not int
            or byte_count < 0
            or type(mtime_ns) is not int
            or mtime_ns < 0
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            return False

    return all(left.get(key) == right.get(key) for key in ("path", "bytes", "sha256"))


def _same_current_source_observation_for_reuse(left: object, right: object) -> bool:
    """Compare source pins exactly except volatile SQLite SHM mtime observations."""
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if left.keys() != right.keys() or not _CURRENT_SOURCE_SHARED_MEMORY_FIELDS.issubset(left.keys()):
        return False
    for key in left:
        if key in _CURRENT_SOURCE_SHARED_MEMORY_FIELDS:
            if not _same_current_source_file_observation(
                left[key],
                right[key],
            ):
                return False
        elif not _exact_current_source_json_identity(left[key], right[key]):
            return False
    return True


def verify_current_observed_cycle_reuse(
    *,
    reuse_terminal_path: str | Path,
    reuse_terminal_sha256: str,
    expected_raw_run_id: str,
    expected_source_date: str,
    require_original_capacity: bool = False,
    formal_output_root: str | Path | None = None,
) -> Mapping[str, Any]:
    """Verify a G6 skipped-same-inputs terminal and its original completed cycle.

    The latest raw run may be a verified reuse rather than a newly completed
    cycle. This validates both immutable terminal files, their shared market,
    scope, source, and B identities, and the original immutable registry
    record. It never treats the newer raw run as the source cycle identity.
    """

    research_roots = _current_observed_research_roots()
    repository_root = Path(_CURRENT_OBSERVED_RESEARCH_ROOT).parents[1]
    def read_json_pin(
        path_value: object,
        expected_sha256: object,
        *,
        label: str,
        maximum_bytes: int = 16 * 1024 * 1024,
    ) -> tuple[Path, Mapping[str, Any]]:
        if type(path_value) is not str or not path_value.strip():
            raise ValueError(f"current-observed reuse {label} path is missing")
        if type(expected_sha256) is not str or not _is_sha256_digest(expected_sha256):
            raise ValueError(f"current-observed reuse {label} hash is invalid")
        requested = Path(path_value)
        if not requested.is_absolute():
            raise ValueError(f"current-observed reuse {label} path is unsafe")
        try:
            validated = resolve_ml_research_output_path(
                requested,
                repository_root=repository_root,
                access="read",
            )
            path = validated.resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"current-observed reuse {label} path is outside approved research output"
            ) from exc
        if (
            path != validated
            or not path.is_file()
            or not _is_below_current_observed_cycle_root(path, research_roots)
        ):
            raise ValueError(f"current-observed reuse {label} path escaped the cycle root")
        before = path.stat()
        if before.st_size > maximum_bytes:
            raise ValueError(f"current-observed reuse {label} exceeds its size bound")
        raw = path.read_bytes()
        after = path.stat()
        if (
            len(raw) != before.st_size
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or "sha256:" + hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise ValueError(f"current-observed reuse {label} hash or stability mismatch")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"current-observed reuse {label} JSON is invalid") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"current-observed reuse {label} root is not an object")
        return path, payload

    reuse_path, reuse_terminal = read_json_pin(
        str(reuse_terminal_path),
        reuse_terminal_sha256,
        label="outer terminal",
    )
    if (
        reuse_terminal.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or reuse_terminal.get("status") != "skipped_same_inputs"
        or reuse_terminal.get("raw_run_id") != expected_raw_run_id
        or reuse_terminal.get("cycle_id") != expected_raw_run_id
        or reuse_terminal.get("source_date") != expected_source_date
        or reuse_terminal.get("historical_pit_eligible") is not False
        or reuse_terminal.get("formal_training_eligible") is not False
        or reuse_terminal.get("production_action_allowed") is not False
    ):
        raise ValueError("current-observed reuse outer terminal identity or flags are invalid")
    outer_pins = reuse_terminal.get("same_run_pins")
    reused_from = reuse_terminal.get("reused_from")
    if not isinstance(outer_pins, Mapping) or not isinstance(reused_from, Mapping):
        raise ValueError("current-observed reuse terminal has no exact input or reuse pins")

    original_path, original_terminal = read_json_pin(
        reused_from.get("terminal_receipt_path"),
        reused_from.get("terminal_receipt_sha256"),
        label="original completed terminal",
    )
    original_run_id = reused_from.get("raw_run_id")
    original_cycle_id = reused_from.get("cycle_id")
    if (
        original_terminal.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or original_terminal.get("status") != "completed"
        or original_terminal.get("raw_run_id") != original_run_id
        or original_terminal.get("cycle_id") != original_cycle_id
        or original_terminal.get("source_date") != expected_source_date
        or original_terminal.get("current_symbols") != reuse_terminal.get("current_symbols")
        or original_run_id == expected_raw_run_id
        or original_cycle_id == expected_raw_run_id
    ):
        raise ValueError("current-observed reuse original terminal identity is invalid")
    original_pins = original_terminal.get("same_run_pins")
    if not isinstance(original_pins, Mapping):
        raise ValueError("current-observed original terminal has no exact source pins")

    for key in (
        "reuse_key_sha256",
        "current_source_observation",
        "current_price_row_fingerprint_sha256_by_symbol",
        "official_raw_input_identity",
        "b_semantic_identity",
    ):
        if key == "current_source_observation":
            same_identity = _same_current_source_observation_for_reuse(
                outer_pins.get(key),
                original_pins.get(key),
            )
        else:
            same_identity = outer_pins.get(key) == original_pins.get(key)
        if not same_identity:
            raise ValueError(f"current-observed reuse input identity differs: {key}")
    reuse_key = outer_pins.get("reuse_key_sha256")
    if type(reuse_key) is not str or not _is_sha256_digest(reuse_key):
        raise ValueError("current-observed reuse key is invalid")

    def read_scope(terminal: Mapping[str, Any], label: str) -> Mapping[str, Any]:
        pins = terminal.get("same_run_pins")
        if not isinstance(pins, Mapping):
            raise ValueError(f"current-observed {label} scope pin is missing")
        scope_path, scope = read_json_pin(
            pins.get("scope_manifest_path"),
            pins.get("scope_manifest_sha256"),
            label=f"{label} scope manifest",
            maximum_bytes=2 * 1024 * 1024,
        )
        if (
            scope.get("schema_version") != "current-stock-research-cycle-scope.v1"
            or scope.get("raw_run_id") != terminal.get("raw_run_id")
            or scope.get("source_date") != expected_source_date
            or scope.get("current_symbols") != terminal.get("current_symbols")
            or Path(str(pins.get("scope_manifest_path") or "")).resolve() != scope_path
        ):
            raise ValueError(f"current-observed {label} scope manifest identity is invalid")
        return scope

    outer_scope = read_scope(reuse_terminal, "reuse")
    original_scope = read_scope(original_terminal, "original")
    for key in (
        "current_symbols",
        "watchlist_symbols",
        "holding_symbols",
        "watchlist_input_pins",
        "position_input_pins",
        "watchlist_storage",
    ):
        if outer_scope.get(key) != original_scope.get(key):
            raise ValueError(f"current-observed reuse scope identity differs: {key}")

    original_registry = original_terminal.get("registry")
    if not isinstance(original_registry, Mapping):
        raise ValueError("current-observed reused cycle registry pin is missing")
    original_registry_record_sha256 = _normalized_sha256_hex(
        original_registry.get("record_sha256")
    )
    reused_registry_record_sha256 = _normalized_sha256_hex(
        reused_from.get("registry_record_sha256")
    )
    if (
        reused_from.get("registry_record_path") != original_registry.get("record_path")
        or original_registry_record_sha256 is None
        or reused_registry_record_sha256 != original_registry_record_sha256
        or reused_from.get("registry_index_path") != original_registry.get("index_path")
        or not _is_sha256_digest(str(reused_from.get("registry_index_sha256_at_reuse") or ""))
    ):
        raise ValueError("current-observed reused registry identity differs from original terminal")
    requested_record_path = Path(str(original_registry.get("record_path") or ""))
    if not requested_record_path.is_absolute() or requested_record_path.is_symlink():
        raise ValueError("current-observed reused registry record path is unsafe")
    try:
        validated_record_path = resolve_ml_research_output_path(
            requested_record_path,
            repository_root=repository_root,
            access="read",
        )
        record_path = validated_record_path.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("current-observed reused registry record path is outside research roots") from exc
    if (
        record_path != validated_record_path
        or not record_path.is_file()
        or not any(_path_is_same_or_child(record_path, root) for root in research_roots)
        or original_registry_record_sha256 is None
        or _sha256_file(record_path) != "sha256:" + original_registry_record_sha256
    ):
        raise ValueError("current-observed reused registry record hash or path is invalid")
    try:
        registry_record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current-observed reused registry record JSON is invalid") from exc
    if (
        not isinstance(registry_record, Mapping)
        or registry_record.get("schema_version") != "current-restated-stock-research-registry.v1"
        or registry_record.get("run_id") != original_registry.get("run_id")
        or registry_record.get("status") != "verified_research_sidecar"
        or registry_record.get("scope_mode") != "current_stock_research"
        or registry_record.get("cycle_id") != original_cycle_id
        or registry_record.get("event_date") != expected_source_date
        or registry_record.get("symbols") != original_terminal.get("current_symbols")
        or registry_record.get("current_price_row_fingerprint_sha256_by_symbol")
        != outer_pins.get("current_price_row_fingerprint_sha256_by_symbol")
        or registry_record.get("historical_pit_eligible") is not False
        or registry_record.get("formal_qualified") is not False
        or registry_record.get("production_action_allowed") is not False
    ):
        raise ValueError("current-observed reused registry record semantics are invalid")

    original_capacity_verified = False
    if require_original_capacity:
        original_research_root = _current_observed_research_root_for_path(
            original_path, research_roots
        )
        if formal_output_root is None or original_research_root is None or not current_stock_research_capacity_passed(
            original_terminal,
            expected_raw_run_id=str(original_run_id or ""),
            expected_source_date=expected_source_date,
            formal_output_root=formal_output_root,
            expected_research_root=original_research_root,
        ):
            raise ValueError("current-observed reused G6 terminal capacity proof is invalid")
        original_capacity_verified = True
    result: dict[str, Any] = {
        "discovery_raw_run_id": expected_raw_run_id,
        "discovery_cycle_id": reuse_terminal.get("cycle_id"),
        "reuse_terminal_path": str(reuse_path),
        "reuse_terminal_sha256": reuse_terminal_sha256,
        "original_raw_run_id": original_run_id,
        "original_cycle_id": original_cycle_id,
        "original_terminal_path": str(original_path),
        "original_terminal_sha256": reused_from.get("terminal_receipt_sha256"),
        "source_date": expected_source_date,
        "reuse_key_sha256": reuse_key,
        "registry_record_path": str(record_path),
        "registry_record_sha256": original_registry.get("record_sha256"),
    }
    if require_original_capacity:
        result["original_capacity_verified"] = original_capacity_verified
    return result


def _validate_current_observed_read_session(
    snapshot: Mapping[str, Any],
    read_session: PinnedSQLiteReadSession,
) -> None:
    if type(read_session) is not PinnedSQLiteReadSession:
        raise TypeError("current-observed pinned read session has an unsupported type")
    source_path_text = snapshot.get("snapshot_database_path")
    source_sha = _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
    if type(source_path_text) is not str or not Path(source_path_text).is_absolute() or source_sha is None:
        raise ValueError("current-observed snapshot database identity is invalid")
    expected_path = Path(source_path_text).resolve(strict=True)
    pins = read_session.source_file_group_start
    if type(pins) is not tuple or not pins:
        raise ValueError("current-observed pinned source file group is unavailable")
    main_pin = pins[0]
    if (
        type(main_pin) is not SQLiteFilePinV1
        or main_pin.role != "main"
        or not main_pin.present
        or main_pin.sha256 != source_sha
        or Path(main_pin.path).resolve(strict=True) != expected_path
    ):
        raise ValueError("current-observed pinned source identity differs from snapshot")
    if not read_session.connection.in_transaction:
        raise ValueError("current-observed pinned SQLite transaction is not active")


def _current_observed_read_session(
    snapshot: Mapping[str, Any],
    resolver: Callable[[Path, str], PinnedSQLiteReadSession],
) -> PinnedSQLiteReadSession:
    source_path_text = snapshot.get("snapshot_database_path")
    source_sha = _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
    if type(source_path_text) is not str or source_sha is None:
        raise ValueError("current-observed snapshot database identity is invalid")
    source_path = Path(source_path_text)
    if not source_path.is_absolute():
        raise ValueError("current-observed snapshot database path is not absolute")
    session = resolver(source_path, source_sha)
    _validate_current_observed_read_session(snapshot, session)
    return session


def load_current_observed_context_from_pinned_snapshot(
    snapshot: Mapping[str, Any],
    *,
    read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
) -> Any:
    """Rehydrate G9 context from immutable G6 snapshot pins without rereading D.

    The ordinary G6 context loader deliberately rechecks the mutable source DB,
    WAL and revision namespace. A current-observed outcome may be matured after
    those canonical files naturally advance, so this separate G9 contract only
    revalidates the exact immutable cycle terminal, snapshot DB, receipt and
    context-envelope bytes that were captured together. The source DB/WAL paths
    remain typed provenance strings; they are never opened by this function.
    """

    if not isinstance(snapshot, Mapping):
        raise ValueError("current-observed pinned snapshot must be an object")
    research_roots = _current_observed_research_roots()
    repository_root = Path(_CURRENT_OBSERVED_RESEARCH_ROOT).parents[1]

    def pinned_path(
        field: str,
        digest_field: str,
        *,
        max_bytes: int | None,
        defer_snapshot_database_hash: bool = False,
    ) -> tuple[Path, bytes | None]:
        value = snapshot.get(field)
        expected = snapshot.get(digest_field)
        if type(value) is not str or not value.strip() or type(expected) is not str:
            raise ValueError(f"current-observed immutable pin is missing: {field}")
        expected_digest = _normalized_sha256_hex(expected)
        if expected_digest is None:
            raise ValueError(f"current-observed immutable hash is invalid: {digest_field}")
        path_input = Path(value)
        if not path_input.is_absolute():
            raise ValueError(f"current-observed immutable path is invalid: {field}")
        try:
            validated = resolve_ml_research_output_path(
                path_input,
                repository_root=repository_root,
                access="read",
            )
            path = validated.resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"current-observed immutable path is outside approved research roots: {field}"
            ) from exc
        if (
            path != validated
            or not path.is_file()
            or not any(_path_is_same_or_child(path, root) for root in research_roots)
        ):
            raise ValueError(f"current-observed immutable path is outside the research root: {field}")
        before = path.stat()
        if max_bytes is not None and before.st_size > max_bytes:
            raise ValueError(f"current-observed immutable file exceeds its bound: {field}")
        if max_bytes is None:
            if defer_snapshot_database_hash:
                return path, None
            actual = _sha256_file(path)
            after = path.stat()
            if (
                before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or _normalized_sha256_hex(actual) != expected_digest
            ):
                raise ValueError(f"current-observed immutable file hash or stability mismatch: {field}")
            return path, None
        raw = path.read_bytes()
        after = path.stat()
        if (
            len(raw) != before.st_size
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or hashlib.sha256(raw).hexdigest() != expected_digest
        ):
            raise ValueError(f"current-observed immutable file hash or stability mismatch: {field}")
        return path, raw

    def aware_clock(payload: Mapping[str, Any], field: str) -> datetime:
        value = payload.get(field)
        if type(value) is not str or not value.strip():
            raise ValueError(f"current-observed context clock is missing: {field}")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"current-observed context clock is invalid: {field}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"current-observed context clock must be aware: {field}")
        return parsed

    def exact_text(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if type(value) is not str or not value.strip():
            raise ValueError(f"current-observed context text is missing: {field}")
        return value

    def exact_digest(payload: Mapping[str, Any], field: str) -> str:
        value = exact_text(payload, field)
        if _normalized_sha256_hex(value) is None:
            raise ValueError(f"current-observed context hash is invalid: {field}")
        return value

    terminal_path, terminal_bytes = pinned_path(
        "cycle_terminal_path", "cycle_terminal_sha256", max_bytes=8 * 1024 * 1024
    )
    receipt_path, receipt_bytes = pinned_path(
        "snapshot_receipt_path", "snapshot_receipt_sha256", max_bytes=8 * 1024 * 1024
    )
    context_path, context_bytes = pinned_path(
        "source_context_envelope_path",
        "source_context_envelope_sha256",
        max_bytes=4 * 1024 * 1024,
    )
    database_path, _ = pinned_path(
        "snapshot_database_path",
        "snapshot_database_sha256",
        max_bytes=None,
        defer_snapshot_database_hash=read_session_resolver is not None,
    )
    assert terminal_bytes is not None and receipt_bytes is not None and context_bytes is not None

    try:
        terminal = json.loads(terminal_bytes.decode("utf-8"))
        receipt = json.loads(receipt_bytes.decode("utf-8"))
        envelope = json.loads(context_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current-observed immutable JSON pin is invalid") from exc
    if not isinstance(terminal, Mapping) or not isinstance(receipt, Mapping) or not isinstance(envelope, Mapping):
        raise ValueError("current-observed immutable JSON pin root must be an object")
    if json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") != context_bytes:
        raise ValueError("current-observed source context envelope is not canonical JSON")
    if (
        terminal.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or terminal.get("status") != "completed"
        or terminal.get("cycle_id") != snapshot.get("cycle_id")
        or terminal.get("raw_run_id") != snapshot.get("raw_run_id")
        or terminal.get("source_date") != snapshot.get("cycle_source_date")
    ):
        raise ValueError("current-observed terminal identity differs from its pins")
    terminal_pins = terminal.get("same_run_pins")
    if not isinstance(terminal_pins, Mapping):
        raise ValueError("current-observed terminal exact snapshot pins are missing")
    for snapshot_field in (
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_context_envelope_path",
        "source_context_envelope_sha256",
    ):
        if snapshot_field.endswith("_sha256"):
            snapshot_digest = _normalized_sha256_hex(snapshot.get(snapshot_field))
            terminal_digest = _normalized_sha256_hex(terminal_pins.get(snapshot_field))
            if snapshot_digest is None or snapshot_digest != terminal_digest:
                raise ValueError(f"current-observed terminal pin differs: {snapshot_field}")
        elif terminal_pins.get(snapshot_field) != snapshot.get(snapshot_field):
            raise ValueError(f"current-observed terminal pin differs: {snapshot_field}")

    if (
        receipt.get("schema_version") not in {
            "integration-consistent-sqlite-snapshot.v1",
            "integration-consistent-sqlite-snapshot.v2",
        }
        or receipt.get("status") != "consistent_snapshot_created"
        or receipt.get("consistency") != "sqlite_backup_from_single_query_only_read_transaction"
        or receipt.get("snapshot_quick_check") != "ok"
        or receipt.get("source_and_revision_bytes_unchanged") is not True
    ):
        raise ValueError("current-observed snapshot receipt qualification is invalid")
    receipt_snapshot = receipt.get("snapshot")
    source_observation = receipt.get("source_observation")
    source_database = source_observation.get("database") if isinstance(source_observation, Mapping) else None
    if (
        not isinstance(receipt_snapshot, Mapping)
        or not isinstance(source_database, Mapping)
        or Path(str(receipt_snapshot.get("path") or "")).resolve() != database_path
        or _normalized_sha256_hex(receipt_snapshot.get("sha256")) is None
        or _normalized_sha256_hex(receipt_snapshot.get("sha256"))
        != _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
        or str(receipt.get("source_database_path") or "")
        != str(source_database.get("path") or "")
        or _normalized_sha256_hex(source_database.get("sha256")) is None
        or (
            receipt.get("source_database_sha256") is not None
            and _normalized_sha256_hex(receipt.get("source_database_sha256")) is None
        )
        or (
            receipt.get("source_database_sha256") is not None
            and _normalized_sha256_hex(source_database.get("sha256"))
            != _normalized_sha256_hex(receipt.get("source_database_sha256"))
        )
    ):
        raise ValueError("current-observed snapshot receipt identity differs from its pins")

    if envelope.get("schema_version") != "ml-current-restated-source-context-envelope.v1":
        raise ValueError("current-observed source context envelope schema is invalid")
    context_payload = envelope.get("source_context")
    if not isinstance(context_payload, Mapping):
        raise ValueError("current-observed source context payload is missing")
    context_payload = dict(context_payload)
    if (
        context_payload.get("current_restated") is not True
        or context_payload.get("historical_pit_eligible") is not False
        or context_payload.get("snapshot_database_path") != str(database_path)
        or _normalized_sha256_hex(context_payload.get("snapshot_database_sha256")) is None
        or _normalized_sha256_hex(context_payload.get("snapshot_database_sha256"))
        != _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
        or context_payload.get("snapshot_receipt_path") != str(receipt_path)
        or _normalized_sha256_hex(context_payload.get("snapshot_receipt_sha256")) is None
        or _normalized_sha256_hex(context_payload.get("snapshot_receipt_sha256"))
        != _normalized_sha256_hex(snapshot.get("snapshot_receipt_sha256"))
    ):
        raise ValueError("current-observed context flags or snapshot identity differ")
    source_database_path = exact_text(context_payload, "source_database_path")
    if not Path(source_database_path).is_absolute():
        raise ValueError("current-observed context source database path must remain absolute provenance")
    training_as_of = aware_clock(context_payload, "training_as_of")
    observed_clock = aware_clock(snapshot, "observed_at")
    captured_clock = aware_clock(terminal_pins, "snapshot_completed_at")
    revision_clock = aware_clock(terminal_pins, "revision_dependencies_verified_at")
    context_training_clock = aware_clock(context_payload, "training_as_of")
    context_revision_clock = aware_clock(context_payload, "revision_dependencies_verified_at")
    if (
        aware_clock(context_payload, "decision_at") > training_as_of
        or aware_clock(context_payload, "source_observed_at") > training_as_of
        or context_revision_clock > context_training_clock
        or context_training_clock != aware_clock(terminal_pins, "current_restated_training_as_of")
        or context_revision_clock != revision_clock
        or revision_clock < captured_clock
        or training_as_of < captured_clock
        or observed_clock < training_as_of
    ):
        raise ValueError("current-observed context and terminal clocks are inconsistent")
    if receipt.get("completed_at") != captured_clock.isoformat():
        raise ValueError("current-observed snapshot receipt clock differs from terminal")
    receipt_database = source_database
    if (
        str(receipt_database.get("path") or "") != source_database_path
        or _normalized_sha256_hex(receipt_database.get("sha256")) is None
        or _normalized_sha256_hex(context_payload.get("source_database_sha256")) is None
        or _normalized_sha256_hex(receipt_database.get("sha256"))
        != _normalized_sha256_hex(context_payload.get("source_database_sha256"))
    ):
        raise ValueError("current-observed source DB provenance differs from snapshot receipt")

    # This validator checks serialized qualifiers and clock/hash syntax only;
    # it does not open original_database_path or any mutable dependency.
    from ml_module.current_restated_research_bridge import _verify_source_context_payload

    _verify_source_context_payload(context_payload, training_as_of.isoformat())
    from data_module.ml_daily_price_revision_gate import (
        VerifiedCurrentRestatedSourceContext,
        VerifiedRevisionDependencyV1,
        VerifiedRevisionNamespaceFileV1,
    )

    def parse_nonnegative_int(value: object, field: str) -> int:
        if type(value) is not int or value < 0:
            raise ValueError(f"current-observed context integer is invalid: {field}")
        return value

    namespace_payload = context_payload.get("revision_namespace_files")
    dependency_payload = context_payload.get("revision_dependency_files")
    evidence_namespaces = context_payload.get("source_revision_evidence_namespaces")
    evidence_files = context_payload.get("source_revision_evidence_files")
    if (
        not isinstance(namespace_payload, list)
        or not isinstance(dependency_payload, list)
        or not isinstance(evidence_namespaces, list)
        or not isinstance(evidence_files, list)
    ):
        raise ValueError("current-observed context typed provenance lists are invalid")
    namespaces = tuple(
        VerifiedRevisionNamespaceFileV1(
            path=exact_text(item, "path"),
            bytes=parse_nonnegative_int(item.get("bytes"), "revision_namespace_files.bytes"),
            mtime_ns=parse_nonnegative_int(item.get("mtime_ns"), "revision_namespace_files.mtime_ns"),
            sha256=exact_digest(item, "sha256"),
        )
        for item in namespace_payload
        if isinstance(item, Mapping)
    )
    dependencies = tuple(
        VerifiedRevisionDependencyV1(
            namespace=exact_text(item, "namespace"),
            role_id=exact_text(item, "role_id"),
            path=exact_text(item, "path"),
            bytes=parse_nonnegative_int(item.get("bytes"), "revision_dependency_files.bytes"),
            mtime_ns=parse_nonnegative_int(item.get("mtime_ns"), "revision_dependency_files.mtime_ns"),
            sha256=exact_digest(item, "sha256"),
            captured_at=aware_clock(item, "captured_at"),
        )
        for item in dependency_payload
        if isinstance(item, Mapping)
    )
    if len(namespaces) != len(namespace_payload) or len(dependencies) != len(dependency_payload):
        raise ValueError("current-observed context typed provenance contains a non-object row")
    if any(type(item) is not str or not item.strip() for item in evidence_namespaces):
        raise ValueError("current-observed context evidence namespace list is invalid")
    evidence_triples: list[tuple[str, str, str]] = []
    for item in evidence_files:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(type(part) is not str or not part.strip() for part in item)
        ):
            raise ValueError("current-observed context evidence file row is invalid")
        digest = item[2].removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("current-observed context evidence file hash is invalid")
        evidence_triples.append((item[0], item[1], item[2]))
    wal_present = context_payload.get("source_wal_present")
    if type(wal_present) is not bool:
        raise ValueError("current-observed context WAL flag is invalid")
    wal_hash_value = context_payload.get("source_wal_sha256")
    if wal_present:
        if type(wal_hash_value) is not str:
            raise ValueError("current-observed context WAL hash is missing")
        exact_digest(context_payload, "source_wal_sha256")
    elif wal_hash_value is not None:
        raise ValueError("absent source WAL cannot carry a hash")
    source_generation = parse_nonnegative_int(context_payload.get("source_generation"), "source_generation")
    context = VerifiedCurrentRestatedSourceContext(
        source_database_path=source_database_path,
        source_database_sha256=exact_digest(context_payload, "source_database_sha256"),
        source_wal_path=exact_text(context_payload, "source_wal_path"),
        source_wal_sha256=wal_hash_value,
        snapshot_database_path=str(database_path),
        snapshot_database_sha256=exact_digest(context_payload, "snapshot_database_sha256"),
        snapshot_receipt_path=str(receipt_path),
        snapshot_receipt_sha256=exact_digest(context_payload, "snapshot_receipt_sha256"),
        decision_at=aware_clock(context_payload, "decision_at"),
        training_as_of=training_as_of,
        source_observed_at=aware_clock(context_payload, "source_observed_at"),
        source_generation=source_generation,
        revision_namespace_files=namespaces,
        revision_namespace_bundle_sha256=exact_digest(context_payload, "revision_namespace_bundle_sha256"),
        source_revision_evidence_schema_version=exact_text(context_payload, "source_revision_evidence_schema_version"),
        source_revision_evidence_scope_id=exact_text(context_payload, "source_revision_evidence_scope_id"),
        source_revision_evidence_cutoff_date=_date(exact_text(context_payload, "source_revision_evidence_cutoff_date")).isoformat(),
        source_revision_evidence_sha256=exact_digest(context_payload, "source_revision_evidence_sha256"),
        source_revision_evidence_namespaces=tuple(evidence_namespaces),
        source_revision_evidence_files=tuple(evidence_triples),
        revision_dependencies_verified_at=context_revision_clock,
        revision_dependency_files=dependencies,
        revision_dependency_bundle_sha256=exact_digest(context_payload, "revision_dependency_bundle_sha256"),
        current_restated=True,
        historical_pit_eligible=False,
        source_wal_present=wal_present,
    )
    from ml_module.current_restated_research_bridge import _source_context_plain_payload

    if _source_context_plain_payload(context) != context_payload:
        raise ValueError("current-observed typed source context does not round-trip exactly")
    if read_session_resolver is not None:
        _current_observed_read_session(snapshot, read_session_resolver)
    return context


def _verify_current_observed_entry_observation(
    snapshot: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    read_session: PinnedSQLiteReadSession | None = None,
) -> None:
    decision_text = str(snapshot.get("decision_date") or "")[:10]
    if str(snapshot.get("cycle_source_date") or "")[:10] != decision_text:
        raise ValueError("same-date entry observation cannot use another market date")
    observed_at_text = str(observation.get("local_observed_at") or "")
    try:
        observed_at = datetime.fromisoformat(observed_at_text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("entry observation local clock is invalid") from exc
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("entry observation local clock must be timezone-aware")
    session_proof = observation.get("entry_session_proof")
    scheduled_close_at, session_proof_sha256 = _verify_current_observed_entry_session_proof(
        decision_text=decision_text,
        observed_at=observed_at,
        proof=session_proof,
    )
    if observation.get("scheduled_market_close_at") != scheduled_close_at:
        raise ValueError("entry observation scheduled market close differs from verified session proof")
    pins = observation.get("entry_price_pin_by_symbol")
    benchmark_pin = observation.get("benchmark_entry_price_pin")
    symbols = snapshot.get("symbols")
    if (
        not isinstance(pins, Mapping)
        or not isinstance(benchmark_pin, Mapping)
        or not isinstance(symbols, list)
        or set(pins) != {str(item) for item in symbols}
    ):
        raise ValueError("entry observation symbol scope is incomplete")
    database_path = Path(str(snapshot.get("snapshot_database_path") or "")).resolve(strict=True)
    expected_database_hash = _normalized_sha256_hex(snapshot.get("snapshot_database_sha256"))
    if expected_database_hash is None:
        raise ValueError("entry observation source database hash is invalid")
    if read_session is None and (
        database_path.is_symlink()
        or _normalized_sha256_hex(_sha256_file(database_path)) != expected_database_hash
    ):
        raise ValueError("entry observation source database hash mismatch")
    if read_session is not None:
        _validate_current_observed_read_session(snapshot, read_session)
    try:
        connection = (
            read_session.connection
            if read_session is not None
            else sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True, timeout=10)
        )
        try:
            for symbol in sorted(str(item) for item in symbols):
                _verify_one_current_observed_entry_pin(
                    connection,
                    pins[symbol],
                    table="daily_prices",
                    symbol=symbol,
                    decision_text=decision_text,
                    observed_at=observed_at,
                    snapshot=snapshot,
                    scheduled_close_at=scheduled_close_at,
                    session_proof_sha256=session_proof_sha256,
                )
            _verify_one_current_observed_entry_pin(
                connection,
                benchmark_pin,
                table="market_indices",
                symbol="TAIEX",
                decision_text=decision_text,
                observed_at=observed_at,
                snapshot=snapshot,
                scheduled_close_at=scheduled_close_at,
                session_proof_sha256=session_proof_sha256,
            )
        finally:
            if read_session is None:
                connection.close()
    except InterruptedError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError(f"entry observation source row revalidation failed: {exc}") from exc
    if read_session is None and _normalized_sha256_hex(_sha256_file(database_path)) != expected_database_hash:
        raise ValueError("entry observation source database changed during verification")


def _verify_current_observed_entry_session_proof(
    *,
    decision_text: str,
    observed_at: datetime,
    proof: object,
) -> tuple[str, str]:
    """Recompute the official regular close and verify its calendar proof/clock."""

    from data_module.twse_quote_observation_capture import SESSION_CLOSE

    if not isinstance(proof, Mapping):
        raise ValueError("entry observation lacks its official session calendar proof")
    expected_day = _date(decision_text)
    expected_close = datetime.combine(
        expected_day,
        SESSION_CLOSE,
        tzinfo=ZoneInfo("Asia/Taipei"),
    ).isoformat()
    calendar = proof.get("calendar_evidence")
    allowed_open_reasons = {
        "twse_holiday_schedule_open",
        "twse_holiday_schedule_explicit_open",
        "twse_holiday_schedule_cache_open",
        "twse_holiday_schedule_cache_explicit_open",
    }
    if (
        proof.get("schema_version") != "recommendation-current-observed-entry-session-proof.v1"
        or proof.get("decision_date") != decision_text
        or proof.get("exchange") != "TWSE_TAIWAN_EQUITIES"
        or proof.get("timezone") != "Asia/Taipei"
        or proof.get("scheduled_market_close_time") != SESSION_CLOSE.isoformat()
        or proof.get("scheduled_market_close_at") != expected_close
        or not isinstance(calendar, Mapping)
        or calendar.get("target_date") != decision_text
        or calendar.get("is_trading_day") is not True
        or calendar.get("reason_code") not in allowed_open_reasons
        or calendar.get("mode") != "hash_bound_official_calendar_cache"
        or proof.get("calendar_evidence_sha256") != _hash_payload(dict(calendar))
        or proof.get("source_available_at") is not None
        or proof.get("historical_pit_eligible") is not False
        or proof.get("formal_training_allowed") is not False
        or proof.get("research_only") is not True
    ):
        raise ValueError("entry observation official session calendar proof is invalid")
    proof_sha256 = proof.get("proof_sha256")
    body = {key: value for key, value in proof.items() if key != "proof_sha256"}
    if not isinstance(proof_sha256, str) or proof_sha256 != _hash_payload(body):
        raise ValueError("entry observation session proof hash mismatch")
    try:
        proof_clock = datetime.fromisoformat(
            str(proof.get("local_observed_at") or "").replace("Z", "+00:00")
        )
        close_clock = datetime.fromisoformat(expected_close)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("entry observation scheduled close or local clock is invalid") from exc
    if (
        proof_clock.tzinfo is None
        or proof_clock.utcoffset() is None
        or proof_clock.astimezone(timezone.utc) != observed_at.astimezone(timezone.utc)
    ):
        raise ValueError("entry observation session proof clock differs from source observation")
    if observed_at.astimezone(timezone.utc) < close_clock.astimezone(timezone.utc):
        raise ValueError("entry observation source clock precedes scheduled market close")
    verify_current_observed_official_calendar_evidence(
        calendar,
        decision_date=expected_day,
        observed_at=observed_at,
    )
    return expected_close, proof_sha256


def verify_current_observed_official_calendar_evidence(
    evidence: Mapping[str, Any],
    *,
    decision_date: date,
    observed_at: datetime,
) -> Mapping[str, Any]:
    """Verify an annual TWSE cache and derive the captured day's open status.

    The current-observed lane requires a frozen official cache artifact with
    its original raw response bytes. A self-hashed calendar mapping or a live
    response hash without retained bytes is not sufficient for later readback.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("official calendar verification clock must be timezone-aware")
    if evidence.get("mode") != "hash_bound_official_calendar_cache":
        raise ValueError("official calendar evidence lacks frozen cache custody")
    if evidence.get("target_date") != decision_date.isoformat():
        raise ValueError("official calendar target date differs from the decision date")
    if decision_date.weekday() >= 5:
        raise ValueError("weekend cannot be accepted as an official open session")
    cache_path_text = evidence.get("path")
    cache_sha256 = evidence.get("cache_file_sha256")
    if (
        type(cache_path_text) is not str
        or not cache_path_text.strip()
        or not _is_sha256_digest(str(cache_sha256 or ""))
    ):
        raise ValueError("official calendar cache path or file SHA is missing")
    requested_path = Path(cache_path_text).expanduser()
    if not requested_path.is_absolute() or requested_path.is_symlink():
        raise ValueError("official calendar cache path is not a plain absolute path")
    resolved_path = requested_path.resolve(strict=True)
    if resolved_path != requested_path or not resolved_path.is_file():
        raise ValueError("official calendar cache path is not an exact regular file")
    for parent in (resolved_path, *resolved_path.parents):
        if parent.is_symlink():
            raise ValueError("official calendar cache path traverses a symlink")

    from data_module.official_trading_calendar_cache import (
        load_verified_twse_calendar_cache,
    )

    verified = load_verified_twse_calendar_cache(
        resolved_path,
        calendar_year=decision_date.year,
        observed_at=observed_at,
    )
    cache_evidence = verified.evidence
    if (
        cache_evidence.get("path") != str(resolved_path)
        or cache_evidence.get("cache_file_sha256") != cache_sha256
        or cache_evidence.get("cache_content_sha256") != evidence.get("cache_content_sha256")
        or cache_evidence.get("source_hash") != evidence.get("source_hash")
        or cache_evidence.get("source") != evidence.get("source")
        or cache_evidence.get("calendar_year") != evidence.get("calendar_year")
        or cache_evidence.get("coverage") != evidence.get("coverage")
        or evidence.get("annual_schedule_scope") != "planned_annual_closures"
    ):
        raise ValueError("official annual calendar cache custody differs from its evidence")

    closure_scope = evidence.get("temporary_closure_scope")
    from data_module.official_trading_calendar_cache import (
        TWSE_TEMPORARY_CLOSURE_POLICY_URL,
    )

    if (
        not isinstance(closure_scope, Mapping)
        or closure_scope.get("provider") != "TWSE"
        or closure_scope.get("policy_url") != TWSE_TEMPORARY_CLOSURE_POLICY_URL
        or closure_scope.get("source_kind") != "official_event_announcement_optional"
        or closure_scope.get("event_evidence_required") is not True
        or closure_scope.get("event_evidence_required_for_unplanned_closure") is not True
        or closure_scope.get("target_date") != decision_date.isoformat()
        or closure_scope.get("status") != "not_captured"
    ):
        raise ValueError("official temporary-closure scope is invalid or unresolved")

    explicit_row = decision_date in verified.schedule
    is_open = verified.schedule.get(decision_date, True)
    expected_reason = (
        "twse_holiday_schedule_cache_explicit_open"
        if explicit_row and is_open
        else "twse_holiday_schedule_cache_open"
        if is_open
        else "twse_holiday_schedule_cache_closed"
    )
    if is_open is not True or evidence.get("is_trading_day") is not True:
        raise ValueError("verified official annual calendar does not mark the day open")
    if evidence.get("reason_code") != expected_reason:
        raise ValueError("official calendar reason does not match the raw annual schedule")
    return verified.evidence


def _verify_one_current_observed_entry_pin(
    connection: sqlite3.Connection,
    pin: object,
    *,
    table: str,
    symbol: str,
    decision_text: str,
    observed_at: datetime,
    snapshot: Mapping[str, Any],
    scheduled_close_at: str,
    session_proof_sha256: str,
) -> None:
    if not isinstance(pin, Mapping):
        raise ValueError("entry price pin is not an object")
    expected_row_values = {
        "table": table,
        "symbol": symbol,
        "source_date": decision_text,
        "raw_close_value": str(pin.get("raw_close_value") or "").strip(),
    }
    if (
        pin.get("schema_version") != "recommendation-current-observed-entry-price-pin.v1"
        or pin.get("symbol") != symbol
        or pin.get("source_date") != decision_text
        or pin.get("source_table") != table
        or pin.get("source_row_values") != expected_row_values
        or pin.get("source_row_sha256") != _hash_payload(expected_row_values)
        or pin.get("cycle_id") != snapshot.get("cycle_id")
        or pin.get("raw_run_id") != snapshot.get("raw_run_id")
        or pin.get("cycle_terminal_path") != snapshot.get("cycle_terminal_path")
        or pin.get("cycle_terminal_sha256") != snapshot.get("cycle_terminal_sha256")
        or pin.get("snapshot_database_path") != snapshot.get("snapshot_database_path")
        or pin.get("snapshot_database_sha256") != snapshot.get("snapshot_database_sha256")
        or pin.get("snapshot_receipt_path") != snapshot.get("snapshot_receipt_path")
        or pin.get("snapshot_receipt_sha256") != snapshot.get("snapshot_receipt_sha256")
        or pin.get("source_context_envelope_path") != snapshot.get("source_context_envelope_path")
        or pin.get("source_context_envelope_sha256") != snapshot.get("source_context_envelope_sha256")
        or pin.get("source_available_at") is not None
        or pin.get("local_observed_at") != observed_at.isoformat()
        or pin.get("scheduled_market_close_at") != scheduled_close_at
        or pin.get("entry_session_proof_sha256") != session_proof_sha256
        or pin.get("current_restated") is not True
        or pin.get("research_only") is not True
        or pin.get("historical_pit_eligible") is not False
        or pin.get("formal_training_allowed") is not False
    ):
        raise ValueError("entry price pin identity, hash, clock, or flags are invalid")
    if table == "daily_prices":
        rows = connection.execute(
            'SELECT "\u8b49\u5238\u4ee3\u865f", "\u65e5\u671f", CAST("\u6536\u76e4\u50f9" AS TEXT) '
            'FROM daily_prices WHERE "\u65e5\u671f" IN (?, ?) AND "\u8b49\u5238\u4ee3\u865f"=?',
            (date.fromisoformat(decision_text).strftime("%Y%m%d"), decision_text, symbol),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("pinned stock entry row is missing or ambiguous")
        raw_symbol, raw_date, raw_close = rows[0]
        if str(raw_symbol).strip() != symbol or str(raw_date)[:10] not in {
            decision_text,
            date.fromisoformat(decision_text).strftime("%Y%m%d"),
        }:
            raise ValueError("pinned stock entry source identity changed")
    elif table == "market_indices" and symbol == "TAIEX":
        rows = connection.execute(
            'SELECT "\u65e5\u671f", CAST(COALESCE("\u6536\u76e4\u50f9", "\u6536\u76e4\u6307\u6578") AS TEXT) '
            'FROM market_indices WHERE "\u65e5\u671f" IN (?, ?)',
            (date.fromisoformat(decision_text).strftime("%Y%m%d"), decision_text),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("pinned TAIEX entry row is missing or ambiguous")
        raw_date, raw_close = rows[0]
        if str(raw_date)[:10] not in {
            decision_text,
            date.fromisoformat(decision_text).strftime("%Y%m%d"),
        }:
            raise ValueError("pinned TAIEX source date changed")
    else:
        raise ValueError("entry price pin table or instrument is unsupported")
    close = _decimal_or_none(raw_close)
    if (
        close is None
        or close <= 0
        or str(raw_close).strip() != expected_row_values["raw_close_value"]
        or format(close, "f") != pin.get("close_price_twd")
    ):
        raise ValueError("pinned entry close differs from the exact source row")


def _normalized_symbol_set(value: object) -> set[str]:
    if not isinstance(value, (list, tuple)):
        return set()
    return {str(symbol).strip() for symbol in value if str(symbol).strip()}


def _require_same_source_row_hashes(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> None:
    if dict(expected) != dict(observed):
        raise ValueError("current-observed source table hashes changed")


def _is_sha256_digest(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _normalized_sha256_hex(value: object) -> str | None:
    """Validate a bare or prefixed lowercase SHA-256 pin without coercion."""
    if type(value) is not str:
        return None
    digest = value[7:] if value.startswith("sha256:") else value
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return None
    return digest


def verified_source_database_for_capture(
    payload: Mapping[str, Any],
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> Path:
    """回傳已由 capture contract 驗證並錨定的來源資料庫。"""

    if payload.get("schema_version") == "recommendation-prediction-capture-bundle.v1":
        raw_bindings = payload.get("source_contract_bindings")
    else:
        raw_bindings = [payload.get("source_contract_binding")]
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ValueError("capture source database anchor is missing")
    source_paths: set[str] = set()
    for binding in raw_bindings:
        contract_payload = _verify_source_contract_binding(
            binding,
            require_ready=True,
            source_binding_verifier=source_binding_verifier,
        )
        source_database = str(contract_payload.get("source_database") or "").strip()
        if not source_database:
            raise ValueError("capture source contract database anchor is missing")
        source_paths.add(str(Path(source_database).expanduser().resolve()))
    if len(source_paths) != 1:
        raise ValueError("capture source database anchors conflict")
    return Path(next(iter(source_paths)))


def verify_natural_maturity_session_proof(
    proof: Mapping[str, Any],
    *,
    capture_date: str,
    label_end_date: str,
    evaluation_at: datetime,
    expected_db_path: str | Path,
) -> Mapping[str, Any]:
    """委派共用 resolver 執行嚴格的交易日 proof 驗證。"""

    if proof.get("horizon_sessions") != 20:
        raise ValueError("natural maturity session horizon must be 20")
    try:
        from data_module.natural_maturity_session_resolver import (
            NaturalMaturitySessionResolver,
        )
    except ImportError as exc:
        raise ValueError("natural maturity session resolver is unavailable") from exc
    return NaturalMaturitySessionResolver.verify_session_proof(
        proof,
        capture_date,
        label_end_date,
        evaluation_at,
        expected_db_path=expected_db_path,
    )


def _verify_source_availability(
    contract_payload: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    capture_at: str,
) -> None:
    """Reject any source artifact that was unavailable at live capture time."""

    try:
        cutoff = _datetime(str(capture_at)).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("capture source contract capture timestamp is invalid") from exc

    def require_available(
        label: str,
        value: object,
        *,
        binding_key: str | None = None,
    ) -> None:
        if value in (None, ""):
            raise ValueError(f"capture source contract {label} availability is missing")
        try:
            available_at = _datetime(str(value)).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"capture source contract {label} availability is invalid") from exc
        if binding_key is not None:
            bound_value = binding.get(binding_key)
            if bound_value in (None, ""):
                raise ValueError(f"capture source contract {binding_key} is missing")
            try:
                bound_at = _datetime(str(bound_value)).astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"capture source contract {binding_key} is invalid") from exc
            if bound_at != available_at:
                raise ValueError(f"capture source contract {label} availability identity mismatch")
        if available_at > cutoff:
            raise ValueError(f"capture source contract {label} available after capture cutoff")

    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    require_available(
        "technical publication",
        technical.get("publication_available_at"),
        binding_key="technical_publication_available_at",
    )
    source_available_ats = technical.get("source_receipt_available_ats")
    if not isinstance(source_available_ats, list) or not source_available_ats:
        raise ValueError("capture source contract technical source availability is missing")
    bound_source_available_ats = binding.get("technical_source_available_ats")
    if not isinstance(bound_source_available_ats, list) or len(bound_source_available_ats) != len(source_available_ats):
        raise ValueError("capture source contract technical source availability identity is missing")
    for index, available_at in enumerate(source_available_ats):
        if _datetime(str(bound_source_available_ats[index])).astimezone(timezone.utc) != _datetime(
            str(available_at)
        ).astimezone(timezone.utc):
            raise ValueError("capture source contract technical source availability identity mismatch")
        require_available(f"technical source receipt {index}", available_at)

    feature_snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(feature_snapshot, Mapping):
        raise ValueError("capture source contract feature snapshot missing")
    require_available(
        "feature snapshot",
        feature_snapshot.get("captured_at"),
        binding_key="feature_snapshot_captured_at",
    )

    corporate = contract_payload.get("corporate_actions")
    corporate = corporate if isinstance(corporate, Mapping) else {}
    adjustment = corporate.get("adjustment_custody")
    adjustment = adjustment if isinstance(adjustment, Mapping) else {}
    require_available(
        "corporate adjustment manifest",
        adjustment.get("available_at"),
        binding_key="corporate_adjustment_available_at",
    )
    event_publication = corporate.get("event_publication")
    event_publication = event_publication if isinstance(event_publication, Mapping) else {}
    require_available(
        "official event publication",
        event_publication.get("source_publication_available_at"),
        binding_key="official_event_available_at",
    )


def _feature_snapshot_fingerprint(
    capture_day: str | date,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    return _hash_payload(
        {
            "capture_decision_date": (
                capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
            ),
            "rows": [
                {
                    "row_id": row.get("row_id"),
                    "symbol": row.get("symbol"),
                    "decision_date": row.get("decision_date"),
                    "feature_as_of_date": row.get("feature_as_of_date"),
                    "feature_available_date": row.get("feature_available_date"),
                    "feature_values": row.get("feature_values"),
                }
                for row in sorted(rows, key=lambda item: (str(item.get("row_id")), str(item.get("symbol"))))
            ],
        }
    )


def _verify_source_contract_dependencies(
    contract_payload: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    """Re-check the immutable raw/technical/event lineage named by a contract."""

    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    publication = technical.get("publication_receipt")
    if not isinstance(publication, Mapping):
        raise ValueError("capture source contract technical publication lineage missing")
    publication_path = Path(str(publication.get("path") or "")).expanduser().resolve()
    if publication_path.is_symlink() or not publication_path.is_file():
        raise ValueError("capture source contract technical publication missing")
    if _sha256_file(publication_path) != publication.get("sha256"):
        raise ValueError("capture source contract technical publication hash mismatch")
    if (
        binding.get("technical_publication_receipt_file_sha256") is not None
        and binding.get("technical_publication_receipt_file_sha256") != publication.get("sha256")
    ):
        raise ValueError("capture source contract technical publication binding mismatch")
    publication_payload = _read_json(publication_path)
    if not _verified_payload_hash(publication_payload, "content_sha256"):
        raise ValueError("capture source contract technical publication content hash mismatch")
    technical_output = publication_payload.get("technical_output")
    if not isinstance(technical_output, Mapping) or not _verified_content_hash(
        technical_output, "content_sha256"
    ):
        raise ValueError("capture source contract technical output hash mismatch")
    if not isinstance(technical_output.get("rows_sha256"), str):
        raise ValueError("capture source contract technical output value hash missing")
    if publication_payload.get("technical_step_status") == "passed" and (
        publication_payload.get("technical_computation_evidence_status") != "verified"
        or not isinstance(publication_payload.get("technical_computation_evidence"), Mapping)
    ):
        raise ValueError("capture source contract technical computation witness missing")
    source_receipts = publication_payload.get("source_receipts")
    if not isinstance(source_receipts, list) or not source_receipts:
        raise ValueError("capture source contract technical source lineage missing")
    for reference in source_receipts:
        if not isinstance(reference, Mapping):
            raise ValueError("capture source contract daily receipt lineage invalid")
        receipt_path = Path(str(reference.get("receipt_path") or "")).expanduser().resolve()
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError("capture source contract daily receipt missing")
        if _sha256_file(receipt_path) != reference.get("receipt_sha256"):
            raise ValueError("capture source contract daily receipt hash mismatch")
        receipt_payload = _read_json(receipt_path)
        if not _verified_payload_hash(receipt_payload, "content_sha256"):
            raise ValueError("capture source contract daily receipt content hash mismatch")
        raw_path = Path(str(reference.get("raw_response_path") or "")).expanduser().resolve()
        if raw_path.is_symlink() or not raw_path.is_file() or not raw_path.is_relative_to(receipt_path.parent):
            raise ValueError("capture source contract raw response lineage invalid")
        if _sha256_file(raw_path) != reference.get("raw_response_sha256"):
            raise ValueError("capture source contract raw response hash mismatch")

    corporate = contract_payload.get("corporate_actions")
    corporate = corporate if isinstance(corporate, Mapping) else {}
    adjustment = corporate.get("adjustment_custody")
    adjustment = adjustment if isinstance(adjustment, Mapping) else {}
    if adjustment.get("prospective_verified") is not True:
        raise ValueError("capture source contract corporate adjustment custody is not ready")
    adjustment_path = Path(str(adjustment.get("manifest_path") or "")).expanduser().resolve()
    adjustment_file_hash = adjustment.get("manifest_file_hash")
    if adjustment_path.is_symlink() or not adjustment_path.is_file() or _sha256_file(adjustment_path) != adjustment_file_hash:
        raise ValueError("capture source contract adjustment manifest hash mismatch")
    if (
        binding.get("corporate_adjustment_manifest_hash") is not None
        and binding.get("corporate_adjustment_manifest_hash") != adjustment.get("manifest_hash")
    ):
        raise ValueError("capture source contract adjustment binding mismatch")
    adjustment_manifest = _read_json(adjustment_path)
    if not _verified_payload_hash(adjustment_manifest, "manifest_hash"):
        raise ValueError("capture source contract adjustment manifest content hash mismatch")
    adjustment_sections = (
        adjustment_manifest.get("adjustments"),
        adjustment_manifest.get("coverage"),
    )
    for section in adjustment_sections:
        if not isinstance(section, Mapping):
            raise ValueError("capture source contract adjustment section missing")
        section_path = (adjustment_path.parent / str(section.get("path") or "")).resolve()
        if section_path.is_symlink() or not section_path.is_file() or _sha256_file(section_path) != section.get("file_hash"):
            raise ValueError("capture source contract adjustment section hash mismatch")
    event_publication = corporate.get("event_publication")
    event_publication = event_publication if isinstance(event_publication, Mapping) else {}
    event_path = Path(str(event_publication.get("manifest_path") or "")).expanduser().resolve()
    if event_path.is_symlink() or not event_path.is_file() or _sha256_file(event_path) != event_publication.get("manifest_file_sha256"):
        raise ValueError("capture source contract event manifest hash mismatch")
    event_manifest = _read_json(event_path)
    if not _verified_payload_hash(event_manifest, "manifest_hash"):
        raise ValueError("capture source contract event manifest content hash mismatch")


def _verified_payload_hash(payload: Mapping[str, Any], field_name: str) -> bool:
    declared = payload.get(field_name)
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        return False
    body = {key: value for key, value in payload.items() if key != field_name}
    return _hash_payload(body) == declared


def _verify_active_model_capture_payload(
    payload: Mapping[str, Any],
    *,
    source_binding_verifier: ScheduledSnapshotSourceBindingVerifier | None = None,
) -> None:
    """Verify an immutable active-model monitor capture before outcome use."""

    required = (
        "schema_version", "capture_id", "capture_as_of_date", "captured_at",
        "active_identity", "active_identity_hash", "active_candidate_id",
        "active_model_id", "active_candidate_root", "active_candidate_frozen_at",
        "active_manifest_hash", "active_artifact_hash", "active_freeze_hash",
        "active_pointer_version", "active_effective_date", "feature_registry_hash",
        "feature_schema_hash", "feature_schema", "label_registry_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
        "probability_lineage", "rows", "capture_hash", "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("active model capture metadata is incomplete")
    if payload.get("schema_version") not in {
        "recommendation-active-model-prediction-capture.v1",
        "recommendation-active-model-prediction-capture.v2",
    }:
        raise ValueError("active model capture schema is unsupported")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload.get("capture_hash"):
        raise ValueError("active model capture hash mismatch")
    try:
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=(
                int(payload["fixed_round_trip_cost_bp"])
                if payload.get("fixed_round_trip_cost_bp") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        raise ValueError(f"active model capture cost scenario is invalid: {exc}") from exc
    if payload.get("schema_version") == "recommendation-active-model-prediction-capture.v2" and not scenario.is_estimated:
        raise ValueError("active model capture v2 must use estimated cost scenario")
    if payload.get("schema_version") == "recommendation-active-model-prediction-capture.v1" and scenario.is_estimated:
        raise ValueError("active model capture v1 cannot use estimated cost scenario")
    expected_label_hash = recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )
    if payload.get("label_registry_hash") != expected_label_hash:
        raise ValueError("active model capture label registry contract mismatch")
    expected_cost_hash = recommendation_cost_contract_hash(
        scenario.fixed_round_trip_cost_bp,
        cost_scenario=scenario if scenario.is_estimated else None,
    )
    if payload.get("cost_contract_hash") != expected_cost_hash:
        raise ValueError("active model capture cost contract mismatch")
    identity = payload.get("active_identity")
    if isinstance(identity, Mapping):
        identity_scenario_hash = str(identity.get("cost_scenario_hash") or "")
        if identity_scenario_hash and identity_scenario_hash != scenario.scenario_hash:
            raise ValueError("active model capture identity cost scenario mismatch")
    capture_day = _date(str(payload["capture_as_of_date"]))
    if _date(str(payload["captured_at"])) > capture_day:
        raise ValueError("active model capture timestamp is after decision cutoff")
    if _datetime(str(payload["active_candidate_frozen_at"])) > _datetime(str(payload["captured_at"])):
        raise ValueError("active candidate freeze is after monitoring capture")
    if payload.get("capture_origin") != "scheduled_active_monitor":
        raise ValueError("active model capture origin is invalid")
    identity = payload.get("active_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("active model identity is invalid")
    if _hash_payload(identity) != payload.get("active_identity_hash"):
        raise ValueError("active model identity hash mismatch")
    for payload_key, identity_key in (
        ("active_candidate_id", "candidate_id"),
        ("active_model_id", "model_id"),
        ("active_candidate_root", "candidate_root"),
        ("active_manifest_hash", "candidate_manifest_hash"),
        ("active_artifact_hash", "candidate_artifact_hash"),
        ("active_freeze_hash", "candidate_freeze_hash"),
    ):
        if str(payload.get(payload_key) or "") != str(identity.get(identity_key) or ""):
            raise ValueError(f"active model identity mismatch: {payload_key}")
    if int(payload["active_pointer_version"]) < 0:
        raise ValueError("active model pointer version is invalid")
    lineage = payload.get("probability_lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("active model probability lineage is missing")
    if payload.get("probability_transform_id") != PROBABILITY_TRANSFORM_ID:
        raise ValueError("active model probability transform is unsupported")
    identity_lineage = identity.get("probability_lineage")
    if identity_lineage != lineage:
        raise ValueError("active model probability lineage mismatch")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("active model capture rows are missing")
    row_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("active model capture row is invalid")
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in row_ids:
            raise ValueError("active model capture row ids must be unique")
        row_ids.add(row_id)
        if _date(str(row.get("decision_date"))) != capture_day:
            raise ValueError("active model capture row decision date mismatch")
        if _date(str(row.get("feature_as_of_date"))) >= capture_day:
            raise ValueError("active model capture feature is not point-in-time")
        if _date(str(row.get("feature_available_date"))) > capture_day:
            raise ValueError("active model capture feature availability is after decision")
        for field_name in ("active_probability_bp", "active_raw_probability_bp"):
            value = row.get(field_name)
            if not isinstance(value, int):
                raise ValueError(f"active model capture {field_name} is missing")
            _probability(value, field_name)
        active_after_cost = row.get("active_after_cost_probability_bp")
        if active_after_cost is not None:
            _probability(int(active_after_cost), "active_after_cost_probability_bp")
        raw_after_cost = row.get("active_raw_after_cost_probability_bp")
        if raw_after_cost is not None:
            _probability(int(raw_after_cost), "active_raw_after_cost_probability_bp")
        if row.get("probability_transform_id") != payload.get("probability_transform_id"):
            raise ValueError("active model capture row probability transform mismatch")
        if row.get("probability_lineage") != lineage:
            raise ValueError("active model capture row probability lineage mismatch")
    source_contract_binding = payload.get("source_contract_binding")
    if source_contract_binding is not None:
        if not isinstance(source_contract_binding, Mapping):
            raise ValueError("active model capture source binding is invalid")
        _verify_source_contract_binding(
            source_contract_binding,
            require_ready=True,
            capture_day=capture_day,
            capture_rows=rows,
            capture_at=str(payload.get("captured_at") or ""),
            source_binding_verifier=source_binding_verifier,
        )


def _brier_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    return sum((int(probability) - int(label) * 10_000) ** 2 for probability, label in zip(probabilities, labels)) // (
        len(labels) * 10_000
    )


def _calibration_gap_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    return abs(sum(probabilities) // len(probabilities) - sum(labels) * 10_000 // len(labels))


def _probability(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{field_name} must be an integer probability bp")


def _scenario_dataclass_kwargs(scenario: RecommendationCostScenario) -> dict[str, Any]:
    """Map a canonical scenario to the optional capture dataclass fields."""

    metadata = scenario.metadata()
    return {
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": (
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
        "cost_scenario": metadata,
    }


def _scenario_fields_from_capture(capture: Any) -> dict[str, Any]:
    """Return only the versioned scenario fields emitted by v3 captures."""

    return {
        "cost_scenario_id": capture.cost_scenario_id,
        "cost_scenario_version": capture.cost_scenario_version,
        "cost_scenario_hash": capture.cost_scenario_hash,
        "cost_basis": capture.cost_basis,
        "cost_policy_id": capture.cost_policy_id,
        "cost_policy_version": capture.cost_policy_version,
        "policy_estimate_date": capture.policy_estimate_date,
        "research_order_amount_twd": capture.research_order_amount_twd,
        "research_order_quantity_shares": capture.research_order_quantity_shares,
        "lot_type": capture.lot_type,
        "instrument_type": capture.instrument_type,
        "cost_scenario": (
            dict(capture.cost_scenario)
            if capture.cost_scenario is not None
            else None
        ),
    }


def _scenario_fields_from_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copy the canonical scenario contract from a capture-like mapping."""

    fields = (
        "cost_scenario_id",
        "cost_scenario_version",
        "cost_scenario_hash",
        "cost_basis",
        "cost_policy_id",
        "cost_policy_version",
        "policy_estimate_date",
        "research_order_amount_twd",
        "research_order_quantity_shares",
        "lot_type",
        "instrument_type",
    )
    result = {key: payload.get(key) for key in fields}
    result["cost_scenario"] = (
        dict(payload["cost_scenario"])
        if isinstance(payload.get("cost_scenario"), Mapping)
        else None
    )
    return result


def _clamp_to_baseline(value: int | None, baseline: int | None, cap: int) -> int | None:
    if value is None or baseline is None:
        return None
    return max(0, min(10_000, max(int(baseline) - cap, min(int(baseline) + cap, int(value)))))


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _datetime(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _verified_content_hash(payload: Mapping[str, Any], field_name: str) -> bool:
    declared = payload.get(field_name)
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        return False
    body = {key: value for key, value in payload.items() if key != field_name}
    return _hash_payload(body) == declared


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_json(path)
        if existing != payload:
            raise RuntimeError("immutable JSON receipt conflict")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _library_versions() -> dict[str, str]:
    import joblib
    import sklearn

    return {"joblib": str(joblib.__version__), "numpy": str(np.__version__), "scikit-learn": str(sklearn.__version__)}
