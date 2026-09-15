"""Static dependency and flag guard for the isolated ML shadow package."""

from __future__ import annotations

import ast
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
ALLOWED_READ_ONLY_PRODUCTION_ML_IMPORTS: dict[str, dict[str, frozenset[str]]] = {
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
            {"ArtifactCompatibilityExpectation", "SafeShadowModelArtifactLoader"}
        ),
        "ml_module.model_artifact_manifest": frozenset({"FeatureSchema"}),
        "ml_module.feature_registry": frozenset({"CORE_LONG_HISTORY_FEATURE_REGISTRY"}),
        "ml_module.recommendation_calibration_training": frozenset(
            {
                "RECOMMENDATION_LABEL_CONTRACT_ID",
                "RecommendationPrediction",
                "recommendation_cost_contract_hash",
                "recommendation_label_registry_hash",
                "candidate_freeze_hash",
            }
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
        "ml_module.recommendation_probability_transform": frozenset(
            {"NULL_BENCHMARK_BASELINE_ID", "PROBABILITY_TRANSFORM_ID"}
        ),
        "ml_module.recommendation_inference_provenance": frozenset(
            {
                "RecommendationProvenanceError",
                "build_inference_projection_receipt",
                "build_inference_provenance",
                "persist_inference_projection_receipt",
                "read_inference_projection_receipt",
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
        return MLShadowBoundaryReport(inspected, tuple(sorted(violations)))

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
