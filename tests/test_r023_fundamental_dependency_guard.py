import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_CONTRACT_MODULES = (
    "data_module/contracts/fundamental.py",
    "data_module/fundamental_availability.py",
    "data_module/fundamental_availability_sources.py",
    "data_module/fundamental_availability_entrypoint.py",
    "data_module/fundamental_data.py",
    "data_module/monthly_revenue_availability_history.py",
    "data_module/monthly_revenue_availability_merge.py",
    "data_module/monthly_revenue_backfill.py",
    "data_module/monthly_revenue_recovery.py",
    "data_module/monthly_revenue_snapshot_harvester.py",
)
FORBIDDEN_FACTOR_NAMES = {
    "FactorDiagnostic",
    "FactorQuality",
    "FactorRecord",
}


def test_fundamental_data_contract_modules_do_not_depend_on_decision_factor_types():
    for relative_path in DATA_CONTRACT_MODULES:
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        decision_imports = []
        factor_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                decision_imports.extend(
                    alias.name
                    for alias in node.names
                    if alias.name == "decision_module"
                    or alias.name.startswith("decision_module.")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "decision_module" or module.startswith("decision_module."):
                    decision_imports.append(module)
                factor_names.extend(
                    alias.name
                    for alias in node.names
                    if alias.name in FORBIDDEN_FACTOR_NAMES
                )
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_FACTOR_NAMES:
                factor_names.append(node.id)

        assert not decision_imports, f"{relative_path}: {decision_imports}"
        assert not factor_names, f"{relative_path}: {factor_names}"


def test_sqlite_monthly_revenue_provider_branch_has_no_factor_type_dependency():
    path = ROOT / "data_module/fundamental_sqlite_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not any(
        (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("decision_module"))
        or (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("decision_module") for alias in node.names)
        )
        for node in module_imports
    )

    monthly_methods = {
        "load_monthly_revenues",
        "_monthly_revenue_record",
        "_monthly_revenue_row_available_date",
        "_monthly_revenue_row_has_formal_availability",
        "_monthly_revenue_row_matches_formal_availability",
        "_monthly_revenue_row_content_fingerprint",
    }
    function_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in monthly_methods
    ]
    assert {node.name for node in function_nodes} == monthly_methods
    for function in function_nodes:
        assert not any(
            isinstance(node, ast.Name) and node.id in FORBIDDEN_FACTOR_NAMES
            for node in ast.walk(function)
        ), f"{function.name} touches a decision factor type"

    statement_converter = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_statement_item_record"
    )
    statement_quality_imports = [
        node
        for node in ast.walk(statement_converter)
        if isinstance(node, ast.ImportFrom)
        and node.module == "decision_module.factors.factor_dtos"
        and any(alias.name == "FactorQuality" for alias in node.names)
    ]
    assert statement_quality_imports == []
    assert any(
        isinstance(node, ast.Name)
        and node.id == "parse_legacy_quality_wire_value"
        for node in ast.walk(statement_converter)
    )


def test_r024_statement_data_and_backfill_keep_factor_interpretation_outside_data():
    for relative in (
        "data_module/contracts/statement.py",
        "data_module/fundamental_statement_data.py",
        "data_module/fundamental_statement_backfill.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports_decision = any(
            (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("decision_module"))
            or (
                isinstance(node, ast.Import)
                and any(alias.name.startswith("decision_module") for alias in node.names)
            )
            for node in ast.walk(tree)
        )
        assert not imports_decision, relative

    decision_adapter = ast.parse(
        (ROOT / "decision_module/factors/statement_factor_adapters.py").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "FactorQuality"
        for node in ast.walk(decision_adapter)
    )
    assert any(
        isinstance(node, ast.Attribute)
        and node.attr == "legacy_quality_wire_value"
        for node in ast.walk(decision_adapter)
    )
