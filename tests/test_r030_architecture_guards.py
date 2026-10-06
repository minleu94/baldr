from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from scripts.check_refactor_architecture_boundary import inspect_root


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "r030"


def _fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "decision_module").mkdir()
    (tmp_path / "app_module" / "recommendation").mkdir(parents=True)
    (tmp_path / "ui_qt" / "views" / "recommendation").mkdir(parents=True)
    (tmp_path / "app_module" / "backtest_service.py").write_text(
        "from decision_module.strategies.registry import StrategyRegistry\n"
        "def resolve(spec): return StrategyRegistry.get_executor(spec)\n",
        encoding="utf-8",
    )
    return tmp_path


def test_repository_boundary_guard_has_no_new_architecture_findings() -> None:
    assert inspect_root(ROOT) == ()


def test_boundary_guard_accepts_registry_routed_positive_fixture(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "decision_module" / "evaluate.py").write_text(
        "def evaluate(value): return value\n", encoding="utf-8"
    )
    (root / "app_module" / "recommendation" / "queries.py").write_text(
        "def read_result(result_id): return result_id\n", encoding="utf-8"
    )
    assert inspect_root(root) == ()


@pytest.mark.parametrize(
    ("fixture_name", "relative_path", "expected_rule"),
    (
        ("decision_imports_app.py", "decision_module/bad.py", "decision_imports_app"),
        (
            "duplicate_row_map.py",
            "app_module/recommendation_replay_service.py",
            "duplicate_row_map",
        ),
        (
            "business_last_state.py",
            "app_module/recommendation/queries.py",
            "business_last_state_read",
        ),
    ),
)
def test_boundary_guard_rejects_bad_architecture_fixtures(
    tmp_path: Path, fixture_name: str, relative_path: str, expected_rule: str
) -> None:
    root = _fixture_root(tmp_path)
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / fixture_name, target)

    findings = inspect_root(root)

    assert any(item.rule == expected_rule and item.path == relative_path for item in findings)


def test_boundary_guard_rejects_strategy_dispatcher_bypass(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    shutil.copyfile(
        FIXTURES / "registry_bypass.py", root / "app_module" / "backtest_service.py"
    )

    findings = inspect_root(root)

    assert any(item.rule == "strategy_registry_bypass" for item in findings)
