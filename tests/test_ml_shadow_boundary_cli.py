"""B01：實際 repo 保留八條歷史違例，不能把 synthetic AST 成功當 repo pass。"""

import json
from pathlib import Path

import pytest

from ml_module.shadow_boundary_guard import MLShadowBoundaryGuard
from scripts.check_ml_shadow_boundary import ROOT, main


LEGACY_VIOLATIONS = (
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.recommendation.queries",
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.saved_recommendation_queries",
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.saved_recommendation_queries",
    "production_imports_ml_module:app_module/personalization_read_service.py:ml_module.recommendation_calibration_evidence:verify_natural_maturity_session_proof",
    "production_imports_ml_module:app_module/recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:InvalidCalibrationOutputError",
    "production_imports_ml_module:app_module/rule_research_label_readiness.py:ml_module.historical_contracts:HistoricalLabelRow",
    "production_imports_ml_module:app_module/rule_research_label_readiness.py:ml_module.historical_contracts:HistoricalLabelSpec",
    "production_imports_ml_module:app_module/stock_research_report_provider_adapters.py:ml_module.current_restated_research_bridge:load_current_restated_outcome_model",
)


def test_shadow_boundary_cli_reports_repository_legacy_violations(capsys) -> None:
    assert main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["inspected_files"] >= 659
    assert report["shadow_only"] is True
    assert tuple(item.replace("\\", "/") for item in report["violations"]) == LEGACY_VIOLATIONS
    assert MLShadowBoundaryGuard(ROOT).inspect().violations


def _inspect_import(tmp_path: Path, source: str, caller: str = "model_registry_readonly.py"):
    app = tmp_path / "app_module"
    app.mkdir()
    (app / caller).write_text(source + "\n", encoding="utf-8")
    return MLShadowBoundaryGuard(tmp_path).inspect()


def test_registry_reader_allows_exact_reviewed_symbols_in_ast(tmp_path: Path) -> None:
    report = _inspect_import(tmp_path, (
        "from ml_module.model_lifecycle_registry import ModelLifecycleEvent as Event, _ALLOWED_TRANSITIONS\n"
        "from ml_module.model_prediction_registries import MLModelRecord as Model"
    ))
    assert report.inspected_files == 1
    assert report.violations == ()


@pytest.mark.parametrize("source", [
    "from ml_module.model_lifecycle_registry import ModelLifecycleRegistry",
    "from ml_module.model_lifecycle_registry import initialize_model_lifecycle_registry",
    "from ml_module.model_prediction_registries import MLModelRegistry",
    "from ml_module.model_prediction_registries import MLShadowPredictionRegistry",
    "from ml_module.model_prediction_registries import initialize_shadow_registry",
    "from ml_module.model_prediction_registries import register_model",
    "from ml_module.model_lifecycle_registry import append",
    "from ml_module.boosted_challengers import BoostedShadowChallengerTrainer",
    "from ml_module.model_lifecycle_registry import *",
    "from ml_module.model_prediction_registries import *",
    "import ml_module.model_lifecycle_registry as registry",
    "from ml_module import model_prediction_registries",
    "from ml_module.model_lifecycle_registry import ModelLifecycleEvent, ModelLifecycleRegistry as EventWriter",
])
def test_registry_reader_rejects_writer_trainer_and_namespace_in_ast(tmp_path: Path, source: str) -> None:
    report = _inspect_import(tmp_path, source)
    assert report.inspected_files == 1
    assert len(report.violations) == 1
    assert report.violations[0].startswith("production_imports_ml_module:")


def test_registry_exact_exception_does_not_allow_another_caller(tmp_path: Path) -> None:
    report = _inspect_import(
        tmp_path, "from ml_module.model_prediction_registries import MLModelRecord", "unreviewed_reader.py",
    )
    assert len(report.violations) == 1
    assert "unreviewed_reader.py" in report.violations[0]
