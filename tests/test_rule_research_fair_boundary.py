from pathlib import Path

from ml_module.shadow_boundary_guard import MLShadowBoundaryGuard


def test_fair_adapter_exact_read_only_imports_allowed(tmp_path: Path):
    path = tmp_path / "app_module" / "rule_research_fair_comparison.py"
    path.parent.mkdir()
    source = Path("app_module/rule_research_fair_comparison.py").read_text(encoding="utf-8")
    path.write_text(source, encoding="utf-8")
    assert MLShadowBoundaryGuard(tmp_path).inspect().violations == ()


def test_fair_adapter_cannot_import_registry_or_training_runner(tmp_path: Path):
    path = tmp_path / "app_module" / "rule_research_fair_comparison.py"
    path.parent.mkdir()
    path.write_text("from ml_module.model_prediction_registries import MLModelRegistry\n"
                    "from ml_module.historical_training_service import HistoricalTrainingService\n", encoding="utf-8")
    violations = MLShadowBoundaryGuard(tmp_path).inspect().violations
    assert len(violations) == 2
    assert all(item.startswith("production_imports_ml_module:") for item in violations)
