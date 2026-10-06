from pathlib import Path

from ml_module.shadow_boundary_guard import MLShadowBoundaryGuard


def test_shadow_acceptance_exact_dto_and_transition_imports_allowed(tmp_path: Path):
    path = tmp_path / "app_module" / "rule_research_shadow_acceptance.py"
    path.parent.mkdir()
    path.write_text(Path("app_module/rule_research_shadow_acceptance.py").read_text(encoding="utf-8"),
                    encoding="utf-8")
    assert MLShadowBoundaryGuard(tmp_path).inspect().violations == ()


def test_shadow_acceptance_cannot_open_registry_or_monitoring_writer(tmp_path: Path):
    path = tmp_path / "app_module" / "rule_research_shadow_acceptance.py"
    path.parent.mkdir()
    path.write_text("from ml_module.model_lifecycle_registry import ModelLifecycleRegistry\n"
                    "from ml_module.shadow_monitoring_service import ShadowMonitoringService\n",
                    encoding="utf-8")
    assert len(MLShadowBoundaryGuard(tmp_path).inspect().violations) == 2
