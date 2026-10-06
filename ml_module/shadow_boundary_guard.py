"""Static dependency and flag guard for the isolated ML shadow package."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


PRODUCTION_ROOTS = (
    "app_module",
    "decision_module",
    "portfolio_module",
    "ui_qt",
    "runtime",
    "backtest_module",
)
FORBIDDEN_ML_IMPORT_ROOTS = frozenset(PRODUCTION_ROOTS)
ARTIFACT_CONTRACT_ROOT = "artifact_contracts"
ARTIFACT_CONTRACT_ALLOWED_EXTERNAL_ROOTS = frozenset({"numpy"})
ALLOWED_READ_ONLY_PRODUCTION_ML_IMPORTS: dict[str, dict[str, frozenset[str]]] = {
    # Sealed research exports only: no training runners or registry I/O.
    "app_module/rule_research_fair_comparison.py": {
        "ml_module.historical_contracts": frozenset({"HistoricalFeatureRow"}),
        "ml_module.historical_feature_builder": frozenset({"HistoricalFeatureBuilder"}),
        "ml_module.feature_registry": frozenset({"CORE_LONG_HISTORY_FEATURE_REGISTRY"}),
        "ml_module.model_prediction_registries": frozenset({"MLModelRecord", "MLShadowPredictionRecord"}),
        "ml_module.inference_contracts": frozenset({"ShadowInferenceRequest", "ShadowPredictionIdentity", "prediction_id_for"}),
        "ml_module.historical_evaluation": frozenset({"evaluate_return_predictions", "evaluate_historical_predictions"}),
    },
    "app_module/ml_allocation_inference_service.py": {
        "ml_module.allocation_contracts": frozenset(
            {"PITFeatureValue", "PortfolioMLDatasetRow"}
        ),
        "ml_module.allocation_training_service": frozenset(
            {
                "ARTIFACT_SCHEMA_VERSION",
                "CLASSIFICATION_EXPERT_HEADS",
                "EXPERT_ALGORITHMS",
                "EXPERT_HEAD_IDS",
                "EXPERT_VECTOR_WIDTH",
                "REGRESSION_EXPERT_HEADS",
            }
        ),
        # 這兩個模組只保存 versioned integer inference contracts；不含
        # application service 或任何資料／交易副作用。
        "ml_module.allocation_family_weight_contract": frozenset(
            {
                "FAMILY_WEIGHT_POLICY_LEGACY_UNKNOWN",
                "FAMILY_WEIGHT_STATUS_LEGACY_UNKNOWN",
                "validate_family_weight_binding",
            }
        ),
        "ml_module.allocation_rank_contract": frozenset(
            {"DEFAULT_RANK_CONTRACT", "rank_values_bp", "validate_rank_contract"}
        ),
    },
    "app_module/ml_allocation_shadow_evidence.py": {
        "ml_module.allocation_contracts": frozenset({"PortfolioMLDatasetRow"}),
        "ml_module.allocation_promotion_reference": frozenset(
            {
                "OUTCOME_CONTRACT_HASH",
                "OUTCOME_CONTRACT_VERSION",
                "PROMOTION_HORIZONS",
                "build_promotion_observation",
                "evaluate_matured_promotion_reference",
            }
        ),
    },
    "app_module/portfolio_allocation_service.py": {
        "ml_module.allocation_validation": frozenset(
            {"AllocationPromotionEvaluator", "PromotionAuthorizationVerifier"}
        ),
    },
    # Release adapter is the single, hash-verified application boundary for
    # optional shadow allocation inference.  It may import only the immutable
    # release and row contracts; production decisions remain fail-closed.
    "app_module/allocation_release_adapter.py": {
        "ml_module.allocation_contracts": frozenset({"PortfolioMLDatasetRow"}),
        "ml_module.allocation_release_contract": frozenset(
            {
                "ARTIFACT_SCHEMA_VERSION",
                "AllocationReleaseManifest",
                "CalibrationBinding",
                "IntegerProbabilityCalibrator",
                "PreprocessorBinding",
                "bytes_hash",
                "payload_hash",
            }
        ),
        # application adapter 將自身實作註冊到中立 loader；producer
        # 不再反向 import app_module。
        "ml_module.allocation_release_loader": frozenset({"register_release_loader"}),
    },
    # Recommendation entries are frozen read-only contracts and verifiers;
    # every imported symbol is listed explicitly instead of allowing a module
    # or namespace wholesale.
    "app_module/recommendation_calibration_consumer.py": {
        "ml_module.model_artifact_loader": frozenset(
            {
                "ArtifactCompatibilityExpectation",
                "SafeShadowModelArtifactLoader",
                "SameBytesShadowModelArtifactWithManifestLoadResultV1",
            }
        ),
        "ml_module.model_artifact_manifest": frozenset(
            {"FeatureSchema", "ModelArtifactManifest"}
        ),
        "ml_module.feature_registry": frozenset({"CORE_LONG_HISTORY_FEATURE_REGISTRY"}),
        "ml_module.recommendation_calibration_training": frozenset(
            {
                "RECOMMENDATION_LABEL_CONTRACT_ID",
                "RECOMMENDATION_RETURN_BASIS",
                "RecommendationPrediction",
                "RunnableRecommendationCalibrationModel",
                "recommendation_cost_contract_hash",
                "recommendation_label_contract_id",
                "recommendation_label_registry_hash",
                "candidate_freeze_hash",
            }
        ),
        "ml_module.probability_calibration": frozenset(
            {"FittedShadowProbabilityCalibrator"}
        ),
        "ml_module.recommendation_cost_scenario": frozenset(
            {
                "LEGACY_RECOMMENDATION_COST_SCENARIO_ID",
                "LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION",
                "RecommendationCostScenario",
                "RecommendationCostScenarioError",
                "cost_scenario_from_metadata",
            }
        ),
        "ml_module.recommendation_calibration_authority": frozenset(
            {"RecommendationPromotionPolicy"}
        ),
        "ml_module.recommendation_probability_transform": frozenset(
            {
                "AFTER_COST_NULL_BENCHMARK_BASELINE_ID",
                "AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP",
                "NULL_BENCHMARK_BASELINE_ID",
                "NULL_BENCHMARK_PROBABILITY_BP",
                "PROBABILITY_LINEAGE_SCHEMA_VERSION",
                "PROBABILITY_TRANSFORM_ID",
                "RecommendationProbabilityTransform",
            }
        ),
        "ml_module.recommendation_inference_provenance": frozenset(
            {
                "RecommendationProvenanceError",
                "build_training_provenance",
                "validate_provenance_compatibility",
                "verify_inference_provenance",
            }
        ),
        "ml_module.recommendation_training_lineage": frozenset(
            {
                "RecommendationTrainingLineageError",
                "read_recommendation_training_lineage",
            }
        ),
        "ml_module.prepared_source_contract": frozenset(
            {"VerifiedSourceContractEvidenceV1"}
        ),
    },
    "app_module/recommendation/historical_snapshot_custody.py": {
        "ml_module.prepared_input_contract": frozenset(
            {
                "AvailabilityBinding",
                "AvailabilityStatus",
                "DateRange",
                "SnapshotKind",
                "SnapshotQualityStatus",
                "SnapshotReference",
                "SnapshotScopeStatus",
            }
        ),
    },
    # 此 adapter 是 R010/R026 typed application boundary，只使用 prepared-input
    # ABI；`_inspect_ml_tree` 仍拒絕 ML 反向 import app。
    "app_module/recommendation/ml_adapter.py": {
        "ml_module.prepared_input_contract": frozenset(
            {"CandidateIdentity", "PreparedMLInput", "SnapshotReference"}
        ),
    },
    "app_module/recommendation/ml_preparation_facts.py": {
        "ml_module.feature_registry": frozenset({"FeatureRegistry"}),
        "ml_module.historical_contracts": frozenset({"HistoricalFeatureRow"}),
        "ml_module.historical_feature_builder": frozenset(
            {
                "HistoricalFeatureBuilder",
                "HistoricalFeatureBuilderLoadContract",
                "HistoricalFeatureVector",
            }
        ),
    },
    "app_module/recommendation/model_resolution_facts.py": {
        "ml_module.model_artifact_manifest": frozenset({"ModelArtifactManifest"}),
    },
    "app_module/recommendation/prepared_runtime_input.py": {
        "ml_module.prepared_input_contract": frozenset(
            {
                "AvailabilityStatus",
                "PreparedMLInput",
                "SnapshotReference",
                "_freeze_aware_datetime",
            }
        ),
        "ml_module.prepared_source_contract": frozenset(
            {"VerifiedSourceContractEvidenceV1"}
        ),
    },
    "app_module/recommendation/prepared_runtime_projector.py": {
        "ml_module.prepared_source_contract": frozenset(
            {"VerifiedSourceContractEvidenceV1"}
        ),
    },
    "app_module/recommendation/prepared_runtime_preparation.py": {
        "ml_module.historical_contracts": frozenset({"HistoricalFeatureRow"}),
        "ml_module.historical_feature_builder": frozenset(
            {"HistoricalFeatureBuilder"}
        ),
        "ml_module.prepared_source_contract": frozenset(
            {"VerifiedSourceContractEvidenceV1"}
        ),
        "ml_module.recommendation_inference_provenance": frozenset(
            {"RecommendationProvenanceError"}
        ),
        "ml_module.recommendation_probability_transform": frozenset(
            {"NULL_BENCHMARK_BASELINE_ID"}
        ),
    },
    "app_module/personalization_projection.py": {
        "ml_module.recommendation_inference_provenance": frozenset(
            {"read_inference_projection_receipt"}
        ),
    },
    "app_module/personalization_save_adapter.py": {
        "ml_module.recommendation_inference_provenance": frozenset(
            {"read_inference_projection_receipt"}
        ),
    },
    "app_module/personalization_action_recorder.py": {
        "ml_module.recommendation_inference_provenance": frozenset(
            {"read_inference_projection_receipt"}
        ),
    },
    "app_module/recommendation/queries.py": {
        "ml_module.recommendation_inference_provenance": frozenset(
            {"read_inference_projection_receipt"}
        ),
    },
    # Cost scenarios are immutable Decimal-backed contracts.  These callers
    # use the typed scenario and metadata parser only; they do not call replay
    # estimators or any file/database writer from the ML package.
    "app_module/recommendation/execute.py": {
        "ml_module.recommendation_cost_scenario": frozenset(
            {
                "RecommendationCostScenario",
                "RecommendationCostScenarioError",
                "cost_scenario_from_metadata",
            }
        ),
    },
    # Personal inventory verifies bounded candidate files before calling the
    # explicitly injected read-only replay service's build().  It does not
    # persist replay results or invoke training/promotion writers.
    "app_module/recommendation/personal_candidate_inventory.py": {
        "ml_module.model_artifact_manifest": frozenset({"ModelArtifactManifest"}),
        "ml_module.recommendation_calibration_training": frozenset(
            {"candidate_freeze_hash"}
        ),
        "ml_module.recommendation_historical_replay": frozenset(
            {
                "RecommendationHistoricalReplayConfig",
                "RecommendationHistoricalReplayService",
            }
        ),
        "ml_module.recommendation_training_lineage": frozenset(
            {"read_recommendation_training_lineage"}
        ),
    },
    # This app adapter calls only the personal projection method and owns its
    # separate create-only output root.  It never calls global evidence scan,
    # persistence, or promotion APIs on the ML service.
    "app_module/recommendation/personal_natural_outcome_daily.py": {
        "ml_module.recommendation_calibration_evidence": frozenset(
            {"verify_natural_maturity_session_proof"}
        ),
        "ml_module.recommendation_natural_outcome_service": frozenset(
            {
                "PersonalNaturalOutcomeProjection",
                "RecommendationNaturalOutcomeService",
            }
        ),
    },
    "app_module/recommendation/personal_prediction_capture.py": {
        "ml_module.recommendation_cost_scenario": frozenset(
            {"RecommendationCostScenarioError", "cost_scenario_from_metadata"}
        ),
    },
    "app_module/recommendation_learning_evidence_projection_service.py": {
        "ml_module.feature_registry": frozenset({"CORE_LONG_HISTORY_FEATURE_REGISTRY"}),
        "ml_module.recommendation_calibration_authority": frozenset(
            {
                "RecommendationNaturalEvidenceComparison",
                "RecommendationNaturalEvidenceVerification",
                "RecommendationPromotionPolicy",
                "verify_natural_evidence_read_only",
            }
        ),
        "ml_module.recommendation_cost_scenario": frozenset(
            {
                "RecommendationCostScenario",
                "RecommendationCostScenarioError",
                "cost_scenario_from_metadata",
            }
        ),
        "ml_module.recommendation_natural_outcome_service": frozenset(
            {"verify_active_model_evidence_payload"}
        ),
        "ml_module.recommendation_calibration_evidence": frozenset(
            {
                "RecommendationPredictionCaptureVerification",
                "verify_prediction_capture_read_only",
            }
        ),
    },
    "app_module/recommendation_service.py": {
        "ml_module.feature_registry": frozenset({"CORE_LONG_HISTORY_FEATURE_REGISTRY"}),
        "ml_module.historical_feature_builder": frozenset({"HistoricalFeatureBuilder"}),
        "ml_module.recommendation_cost_scenario": frozenset(
            {"RecommendationCostScenario"}
        ),
        "ml_module.recommendation_probability_transform": frozenset(
            {"NULL_BENCHMARK_BASELINE_ID", "PROBABILITY_TRANSFORM_ID"}
        ),
        "ml_module.recommendation_inference_provenance": frozenset(
            {
                "RecommendationProvenanceError",
                "build_inference_projection_receipt",
                "build_inference_provenance",
                "build_inference_provenance_with_source_evidence_v1",
                "persist_inference_projection_receipt",
                "read_inference_projection_receipt",
                "verify_inference_provenance",
            }
        ),
    },
}
FORBIDDEN_TRUE_FLAGS = frozenset(
    {
        "production_eligible",
        "production_action_allowed",
        "auto_promotion_allowed",
        "apply_promotion",
        "production_scheduler_allowed",
        "trading_allowed",
    }
)


@dataclass(frozen=True)
class MLShadowBoundaryReport:
    inspected_files: int
    violations: tuple[str, ...]
    shadow_only: bool = True


class MLShadowBoundaryGuard:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def inspect(self) -> MLShadowBoundaryReport:
        violations: list[str] = []
        inspected = 0
        ml_root = self.root / "ml_module"
        for path in sorted(ml_root.rglob("*.py")) if ml_root.exists() else ():
            inspected += 1
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            violations.extend(self._inspect_ml_tree(path, tree))
        for root_name in PRODUCTION_ROOTS:
            package_root = self.root / root_name
            if not package_root.exists():
                continue
            for path in sorted(package_root.rglob("*.py")):
                inspected += 1
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
                relative = path.relative_to(self.root).as_posix()
                allowed = ALLOWED_READ_ONLY_PRODUCTION_ML_IMPORTS.get(
                    relative,
                    {},
                )
                for module, symbol in _import_bindings(tree):
                    if (
                        module == "ml_module"
                        or module.startswith("ml_module.")
                    ):
                        allowed_symbols = allowed.get(module, frozenset())
                        if symbol is None or symbol not in allowed_symbols:
                            imported = module if symbol is None else f"{module}:{symbol}"
                            violations.append(
                                f"production_imports_ml_module:{path.relative_to(self.root)}:{imported}"
                            )
        contract_root = self.root / ARTIFACT_CONTRACT_ROOT
        for path in (
            sorted(contract_root.rglob("*.py"))
            if contract_root.exists()
            else ()
        ):
            inspected += 1
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            violations.extend(self._inspect_artifact_contract_tree(path, tree))
        return MLShadowBoundaryReport(inspected, tuple(sorted(violations)))

    def _inspect_artifact_contract_tree(
        self,
        path: Path,
        tree: ast.AST,
    ) -> tuple[str, ...]:
        """Keep the shared serialized-type leaf independent and statically closed."""

        violations: list[str] = []
        relative = path.relative_to(self.root)
        module_parts = list(relative.with_suffix("").parts)
        package_parts = module_parts[:-1]

        def check_absolute(module: str) -> None:
            root_name = module.split(".", 1)[0]
            if root_name == ARTIFACT_CONTRACT_ROOT:
                return
            if root_name in {
                "builtins",
                "importlib",
                "pkgutil",
                "pydoc",
                "runpy",
            }:
                violations.append(
                    f"artifact_contracts_dynamic_import:{relative}:{module}"
                )
                return
            if (
                root_name not in sys.stdlib_module_names
                and root_name not in ARTIFACT_CONTRACT_ALLOWED_EXTERNAL_ROOTS
            ):
                violations.append(
                    f"artifact_contracts_imports_non_neutral_dependency:{relative}:{module}"
                )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    check_absolute(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    ascend = node.level - 1
                    base = package_parts[: max(0, len(package_parts) - ascend)]
                    target_parts = base + (
                        node.module.split(".") if node.module else []
                    )
                    target = ".".join(target_parts)
                    if ascend >= len(package_parts) or not (
                        target == ARTIFACT_CONTRACT_ROOT
                        or target.startswith(f"{ARTIFACT_CONTRACT_ROOT}.")
                    ):
                        violations.append(
                            f"artifact_contracts_relative_import_escape:{relative}:"
                            f".{'.' * (node.level - 1)}{node.module or ''}"
                        )
                elif node.module:
                    check_absolute(node.module)
            elif isinstance(node, ast.Name) and node.id in {
                "__import__",
                "eval",
                "exec",
            }:
                violations.append(
                    f"artifact_contracts_dynamic_import:{relative}:{node.id}"
                )
            elif isinstance(node, ast.Attribute) and node.attr == "import_module":
                violations.append(
                    f"artifact_contracts_dynamic_import:{relative}:import_module"
                )
        return tuple(violations)

    def _inspect_ml_tree(self, path: Path, tree: ast.AST) -> tuple[str, ...]:
        violations: list[str] = []
        relative = path.relative_to(self.root)
        for module, _symbol in _import_bindings(tree):
            if module.split(".", 1)[0] in FORBIDDEN_ML_IMPORT_ROOTS:
                violations.append(f"ml_imports_production_path:{relative}:{module}")
        for node in ast.walk(tree):
            name: str | None = None
            value: ast.AST | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, value = node.target.id, node.value
            if name in FORBIDDEN_TRUE_FLAGS and isinstance(value, ast.Constant) and value.value is True:
                violations.append(f"forbidden_true_flag:{relative}:{name}")
        return tuple(violations)


def _import_bindings(tree: ast.AST) -> tuple[tuple[str, str | None], ...]:
    bindings: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bindings.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            bindings.extend((node.module, alias.name) for alias in node.names)
    return tuple(bindings)
