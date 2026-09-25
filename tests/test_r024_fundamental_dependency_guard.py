from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
R024_DATA_MODULES = (
    "data_module/fundamental_statement_data.py",
    "data_module/fundamental_statement_availability_sources.py",
    "data_module/fundamental_statement_availability_entrypoint.py",
    "data_module/fundamental_statement_backfill.py",
    "data_module/contracts/statement.py",
    "data_module/valuation_data.py",
    "data_module/valuation_metrics_backfill.py",
    "data_module/contracts/valuation.py",
    "data_module/fundamental_sqlite_provider.py",
)


def _decision_imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                alias.name
                for alias in node.names
                if alias.name.startswith("decision_module")
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("decision_module"):
                imports.append(module)
    return tuple(imports)


def test_r024_data_source_modules_do_not_import_decision_factor_policy() -> None:
    violations = {
        relative: _decision_imports(ROOT / relative)
        for relative in R024_DATA_MODULES
        if _decision_imports(ROOT / relative)
    }

    assert violations == {}
