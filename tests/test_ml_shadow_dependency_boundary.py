import ast
from pathlib import Path

from ml_module.shadow_boundary_guard import MLShadowBoundaryGuard


ROOT = Path(__file__).resolve().parents[1]


def test_repository_respects_ml_shadow_dependency_boundary() -> None:
    report = MLShadowBoundaryGuard(ROOT).inspect()

    assert report.violations == ()
    assert report.shadow_only is True


def test_repaired_input_contract_has_no_app_script_or_data_provider_imports() -> None:
    path = ROOT / "ml_module" / "allocation_repaired_input_contract.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint({"app_module", "data_module", "scripts"})


def test_guard_detects_production_import_of_ml_module(tmp_path: Path) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "bad.py").write_text(
        "from ml_module.boosted_challengers import BoostedShadowChallengerTrainer\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any("production_imports_ml_module" in item for item in report.violations)


def test_guard_requires_exact_symbol_for_allowlisted_module(tmp_path: Path) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "ml_allocation_inference_service.py").write_text(
        "from ml_module.allocation_contracts import UnreviewedTrainingHelper\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any(
        "production_imports_ml_module" in item
        and "allocation_contracts:UnreviewedTrainingHelper" in item
        for item in report.violations
    )


def test_guard_rejects_production_import_of_training_runner(tmp_path: Path) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "consumer.py").write_text(
        "from ml_module.recommendation_calibration_learning_runner import "
        "DailyRecommendationLearningRunner\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any(
        "production_imports_ml_module" in item
        and "recommendation_calibration_learning_runner:DailyRecommendationLearningRunner" in item
        for item in report.violations
    )


def test_guard_allows_only_hash_bound_allocation_inference_contracts(
    tmp_path: Path,
) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "ml_allocation_inference_service.py").write_text(
        "from ml_module.allocation_contracts import PITFeatureValue\n"
        "from ml_module.allocation_training_service import ARTIFACT_SCHEMA_VERSION\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()


def test_guard_allows_only_shadow_evidence_contracts_and_frozen_reference(
    tmp_path: Path,
) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "ml_allocation_shadow_evidence.py").write_text(
        "from ml_module.allocation_contracts import PortfolioMLDatasetRow\n"
        "from ml_module.allocation_promotion_reference import "
        "evaluate_matured_promotion_reference\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()


def test_guard_allows_portfolio_consumer_side_promotion_verifier(
    tmp_path: Path,
) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "portfolio_allocation_service.py").write_text(
        "from ml_module.allocation_validation import "
        "PromotionAuthorizationVerifier\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()


def test_guard_allows_only_hash_verified_release_adapter_contracts(
    tmp_path: Path,
) -> None:
    (tmp_path / "app_module").mkdir()
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "app_module" / "allocation_release_adapter.py").write_text(
        "from ml_module.allocation_contracts import PortfolioMLDatasetRow\n"
        "from ml_module.allocation_release_contract import AllocationReleaseManifest\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()


def test_guard_detects_ml_import_of_production_decision_path(tmp_path: Path) -> None:
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "ml_module" / "bad.py").write_text(
        "from decision_module.scoring import ScoringEngine\n", encoding="utf-8"
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any("ml_imports_production_path" in item for item in report.violations)


def test_guard_detects_ml_backimport_of_app_path(tmp_path: Path) -> None:
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "ml_module" / "bad.py").write_text(
        "from app_module.recommendation_calibration_consumer import "
        "RecommendationCalibrationConsumer\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any("ml_imports_production_path" in item for item in report.violations)


def test_guard_detects_true_production_flag(tmp_path: Path) -> None:
    (tmp_path / "ml_module").mkdir()
    (tmp_path / "ml_module" / "bad.py").write_text(
        "production_eligible = True\n", encoding="utf-8"
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert any("forbidden_true_flag" in item for item in report.violations)


def test_guard_allows_only_reviewed_r026_app_to_ml_edges(tmp_path: Path) -> None:
    imports_by_path = {
        "app_module/recommendation/prepared_runtime_input.py": (
            "from ml_module.prepared_input_contract import ("
            "AvailabilityStatus, PreparedMLInput, SnapshotReference, _freeze_aware_datetime)\n"
            "from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1\n"
        ),
        "app_module/recommendation/prepared_runtime_projector.py": (
            "from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1\n"
        ),
        "app_module/recommendation/prepared_runtime_preparation.py": (
            "from ml_module.historical_contracts import HistoricalFeatureRow\n"
            "from ml_module.historical_feature_builder import HistoricalFeatureBuilder\n"
            "from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1\n"
            "from ml_module.recommendation_inference_provenance import RecommendationProvenanceError\n"
            "from ml_module.recommendation_probability_transform import "
            "NULL_BENCHMARK_BASELINE_ID\n"
        ),
        "app_module/recommendation_calibration_consumer.py": (
            "from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1\n"
            "from ml_module.model_artifact_loader import SameBytesShadowModelArtifactWithManifestLoadResultV1\n"
            "from ml_module.model_artifact_manifest import ModelArtifactManifest\n"
            "from ml_module.probability_calibration import FittedShadowProbabilityCalibrator\n"
            "from ml_module.recommendation_calibration_training import ("
            "RECOMMENDATION_RETURN_BASIS, RunnableRecommendationCalibrationModel, "
            "recommendation_label_contract_id)\n"
        ),
        "app_module/recommendation_service.py": (
            "from ml_module.recommendation_inference_provenance import "
            "build_inference_provenance_with_source_evidence_v1, "
            "verify_inference_provenance\n"
        ),
        "app_module/recommendation/historical_snapshot_custody.py": (
            "from ml_module.prepared_input_contract import ("
            "AvailabilityBinding, AvailabilityStatus, DateRange, SnapshotKind, "
            "SnapshotQualityStatus, SnapshotReference, SnapshotScopeStatus)\n"
        ),
        "app_module/recommendation/ml_adapter.py": (
            "from ml_module.prepared_input_contract import "
            "CandidateIdentity, PreparedMLInput, SnapshotReference\n"
        ),
        "app_module/recommendation/ml_preparation_facts.py": (
            "from ml_module.feature_registry import FeatureRegistry\n"
            "from ml_module.historical_contracts import HistoricalFeatureRow\n"
            "from ml_module.historical_feature_builder import ("
            "HistoricalFeatureBuilder, HistoricalFeatureBuilderLoadContract, "
            "HistoricalFeatureVector)\n"
        ),
        "app_module/recommendation/model_resolution_facts.py": (
            "from ml_module.model_artifact_manifest import ModelArtifactManifest\n"
        ),
        "app_module/personalization_projection.py": (
            "from ml_module.recommendation_inference_provenance import "
            "read_inference_projection_receipt\n"
        ),
        "app_module/personalization_save_adapter.py": (
            "from ml_module.recommendation_inference_provenance import "
            "read_inference_projection_receipt\n"
        ),
        "app_module/recommendation/queries.py": (
            "from ml_module.recommendation_inference_provenance import "
            "read_inference_projection_receipt\n"
        ),
    }
    for relative_path, source in imports_by_path.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()


def test_guard_rejects_unlisted_symbol_from_each_reviewed_r026_leaf(
    tmp_path: Path,
) -> None:
    cases = (
        (
            "app_module/recommendation/prepared_runtime_input.py",
            "ml_module.prepared_input_contract",
            "UnreviewedPreparedInputOverride",
        ),
        (
            "app_module/recommendation/prepared_runtime_input.py",
            "ml_module.prepared_source_contract",
            "UnreviewedSourceEvidenceOverride",
        ),
        (
            "app_module/recommendation_service.py",
            "ml_module.recommendation_inference_provenance",
            "unreviewed_provenance_helper",
        ),
        (
            "app_module/recommendation_calibration_consumer.py",
            "ml_module.model_artifact_loader",
            "UnreviewedShadowLoaderResult",
        ),
        (
            "app_module/recommendation_calibration_consumer.py",
            "ml_module.model_artifact_manifest",
            "UnreviewedManifestHelper",
        ),
        (
            "app_module/recommendation_calibration_consumer.py",
            "ml_module.probability_calibration",
            "UnreviewedCalibrationHelper",
        ),
        (
            "app_module/recommendation_calibration_consumer.py",
            "ml_module.recommendation_calibration_training",
            "UnreviewedTrainingHelper",
        ),
        (
            "app_module/recommendation/ml_preparation_facts.py",
            "ml_module.feature_registry",
            "UnreviewedFeatureRegistryAPI",
        ),
        (
            "app_module/recommendation/ml_preparation_facts.py",
            "ml_module.historical_contracts",
            "UnreviewedTrainingRow",
        ),
        (
            "app_module/recommendation/ml_preparation_facts.py",
            "ml_module.historical_feature_builder",
            "UnreviewedTrainingRunner",
        ),
        (
            "app_module/recommendation/prepared_runtime_preparation.py",
            "ml_module.historical_feature_builder",
            "UnreviewedPreparationRunner",
        ),
        (
            "app_module/recommendation/prepared_runtime_preparation.py",
            "ml_module.prepared_source_contract",
            "UnreviewedSourceEvidenceOverride",
        ),
        (
            "app_module/recommendation/prepared_runtime_preparation.py",
            "ml_module.recommendation_inference_provenance",
            "verify_inference_provenance",
        ),
        (
            "app_module/recommendation/historical_snapshot_custody.py",
            "ml_module.prepared_input_contract",
            "UnreviewedSnapshotStore",
        ),
        (
            "app_module/recommendation/ml_adapter.py",
            "ml_module.prepared_input_contract",
            "UnreviewedModelLoader",
        ),
        (
            "app_module/recommendation/model_resolution_facts.py",
            "ml_module.model_artifact_manifest",
            "UnreviewedManifestLoader",
        ),
        (
            "app_module/personalization_projection.py",
            "ml_module.recommendation_inference_provenance",
            "build_inference_provenance",
        ),
        (
            "app_module/personalization_save_adapter.py",
            "ml_module.recommendation_inference_provenance",
            "persist_inference_projection_receipt",
        ),
        (
            "app_module/recommendation/queries.py",
            "ml_module.recommendation_inference_provenance",
            "verify_inference_provenance",
        ),
    )
    for index, (relative_path, module, symbol) in enumerate(cases):
        case_root = tmp_path / str(index)
        path = case_root / relative_path
        path.parent.mkdir(parents=True)
        path.write_text(
            f"from {module} import {symbol}\n",
            encoding="utf-8",
        )

        report = MLShadowBoundaryGuard(case_root).inspect()

        assert any(
            item.endswith(f"{module}:{symbol}") for item in report.violations
        ), relative_path


def test_new_provenance_edges_remain_source_scoped_and_symbol_exact(
    tmp_path: Path,
) -> None:
    cases = (
        (
            "app_module/recommendation/prepared_runtime_preparation.py",
            "from ml_module.recommendation_inference_provenance import *\n",
            "ml_module.recommendation_inference_provenance:*",
        ),
        (
            "app_module/recommendation/prepared_runtime_preparation.py",
            "import ml_module.recommendation_inference_provenance\n",
            "ml_module.recommendation_inference_provenance",
        ),
        (
            "app_module/recommendation_service.py",
            "from ml_module.recommendation_inference_provenance import "
            "UnreviewedReceiptHelper\n",
            "ml_module.recommendation_inference_provenance:UnreviewedReceiptHelper",
        ),
    )
    for index, (relative_path, source, diagnostic_suffix) in enumerate(cases):
        case_root = tmp_path / f"source-scoped-{index}"
        path = case_root / relative_path
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding="utf-8")

        report = MLShadowBoundaryGuard(case_root).inspect()

        assert any(
            item.endswith(diagnostic_suffix) for item in report.violations
        ), relative_path


def test_artifact_contract_root_rejects_cross_boundary_and_dynamic_imports(
    tmp_path: Path,
) -> None:
    cases = (
        (
            "from ml_module.allocation_contracts import PortfolioMLDatasetRow\n",
            "artifact_contracts_imports_non_neutral_dependency",
        ),
        (
            "import app_module.application_ports\n",
            "artifact_contracts_imports_non_neutral_dependency",
        ),
        (
            "from ..ml_module.allocation_contracts import PortfolioMLDatasetRow\n",
            "artifact_contracts_relative_import_escape",
        ),
        (
            "from ..artifact_contracts import allocation_model_types\n",
            "artifact_contracts_relative_import_escape",
        ),
        (
            "from importlib import import_module\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "import pkgutil\n"
            "pkgutil.resolve_name('ml_module.allocation_contracts.PortfolioMLDatasetRow')\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "from pkgutil import get_loader\n"
            "get_loader('ml_module.allocation_contracts')\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "import pydoc\n"
            "pydoc.locate('ml_module.allocation_contracts.PortfolioMLDatasetRow')\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "from pydoc import importfile\n"
            "importfile('ml_module/allocation_contracts.py')\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "def load(name):\n    return __import__(name)\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "eval(\"__import__('ml_module')\")\n",
            "artifact_contracts_dynamic_import",
        ),
        (
            "exec(\"import ml_module\")\n",
            "artifact_contracts_dynamic_import",
        ),
    )
    for index, (source, diagnostic) in enumerate(cases):
        case_root = tmp_path / str(index)
        path = case_root / "artifact_contracts" / "allocation_model_types.py"
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding="utf-8")

        report = MLShadowBoundaryGuard(case_root).inspect()

        assert any(item.startswith(diagnostic) for item in report.violations), source


def test_artifact_contract_root_allows_standard_library_numpy_and_internal_imports(
    tmp_path: Path,
) -> None:
    package = tmp_path / "artifact_contracts"
    (package / "sub").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaf.py").write_text(
        "from dataclasses import dataclass\n"
        "import numpy as np\n"
        "@dataclass(frozen=True)\n"
        "class Leaf:\n    value: int\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from .leaf import Leaf\n",
        encoding="utf-8",
    )
    (package / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (package / "sub" / "consumer.py").write_text(
        "from ..leaf import Leaf\n",
        encoding="utf-8",
    )

    report = MLShadowBoundaryGuard(tmp_path).inspect()

    assert report.violations == ()
