"""重建測試資產候選清冊，並輸出可審閱的 bounded QA 證據。

本工具只讀取 repository 內的測試、QA script、文件與設定檔，使用 Python AST
及檔案結構產生候選清冊。它不匯入 production module、不存取 DATA_ROOT、
不呼叫網路、不執行 pytest，也不修改測試或正式資料。

需要特別區分兩件事：

* member inventory 是把候選成員以路徑、qualified name 與起始行號重建；
* semantic review 是逐一核對業務契約、mutable state、teardown 與回歸證據。

本工具只對少數明確標記的候選完成 focused／架構 review；B/C 其餘候選完成
逐組的靜態候選處置，保留並輸出每組自己的證據與缺口，不把 AST 相似誤寫成
可安全整併或語意等價證明。
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import copy
import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "qa" / "test_asset_audit"
TOP_C_REVIEWED = {"DUP-C-013", "DUP-C-016", "DUP-C-024", "DUP-C-025", "DUP-C-036"}
REVIEWED_C_PATHS = {
    "DUP-C-013": "tests/test_formal_daily_input_producer.py",
    "DUP-C-016": "tests/test_forward_position_thesis_candidate_producer.py",
    "DUP-C-024": "tests/test_paper_daily_execution_producer.py",
    "DUP-C-025": "tests/test_paper_formal_daily_source_chain.py",
    "DUP-C-036": "tests/test_recommendation_service_calibration_integration.py",
}
MANUAL_PREFIX = "tests/manual/"
INTERNAL_PREFIX = "tests/scripts/"


class TestFunctionVisitor(ast.NodeVisitor):
    """Extract test functions without importing the target test modules."""

    def __init__(self, rel_path: str, module_metadata: dict[str, Any]) -> None:
        self.rel_path = rel_path
        self.module_metadata = module_metadata
        self.class_stack: list[str] = []
        self.functions: list[dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node)
        self.generic_visit(node)

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not (node.name.startswith("test_") or node.name.endswith("_test")):
            return

        qualified_name = ".".join(self.class_stack + [node.name])
        end_line = getattr(node, "end_lineno", node.lineno)
        assertions = [child for child in ast.walk(node) if isinstance(child, ast.Assert)]
        calls = [self._call_name(child) for child in ast.walk(node) if isinstance(child, ast.Call)]
        calls = [call for call in calls if call]
        setup_nodes = list(node.body)
        if setup_nodes and self._is_docstring(setup_nodes[0]):
            setup_nodes = setup_nodes[1:]
        first_assert = next(
            (index for index, statement in enumerate(setup_nodes) if any(isinstance(child, ast.Assert) for child in ast.walk(statement))),
            len(setup_nodes),
        )
        setup_prefix = setup_nodes[:first_assert]
        boundary = any(
            token in node.name.lower()
            for token in ("boundary", "cutoff", "edge", "zero", "empty", "tamper", "corrupt", "retry", "rollback")
        )

        self.functions.append(
            {
                "rel_path": self.rel_path,
                "qual_name": qualified_name,
                "start_line": node.lineno,
                "end_line": end_line,
                "line_count": end_line - node.lineno + 1,
                "member_id": f"{self.rel_path}::{qualified_name}:{node.lineno}",
                "fixture_dependencies": [
                    argument.arg
                    for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                    if argument.arg not in {"self", "cls"}
                ],
                "decorators": [ast.unparse(decorator) for decorator in node.decorator_list],
                "assertions": [ast.unparse(child) for child in assertions],
                "raises_contexts": [
                    ast.unparse(child)
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "raises"
                ],
                "literal_values": literal_values(node),
                "module_imports": self.module_metadata["module_imports"],
                "production_imports": self.module_metadata["production_imports"],
                "module_helpers": self.module_metadata["module_helpers"],
                "module_fixtures": self.module_metadata["module_fixtures"],
                "module_constants": self.module_metadata["module_constants"],
                "assertion_count": len(assertions),
                "calls": calls,
                "setup_calls": sorted({call for statement in setup_prefix for call in self._calls_in(statement)}),
                "setup_statement_count": len(setup_prefix),
                "setup_line_count": max(0, len(node.body) - len(assertions)),
                "is_boundary": boundary,
                "exact_hash": normalize_exact(node),
                "near_hash": normalize_near(node),
                "setup_hash": normalize_nodes(setup_prefix, normalize_literals=True),
                "setup_exact_hash": normalize_nodes(setup_prefix, normalize_literals=False),
            }
        )

    @staticmethod
    def _is_docstring(node: ast.stmt) -> bool:
        return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    @classmethod
    def _calls_in(cls, node: ast.AST) -> list[str]:
        return [name for child in ast.walk(node) if isinstance(child, ast.Call) for name in [cls._call_name(child)] if name]


class StructuralNormalizer(ast.NodeTransformer):
    def __init__(self, normalize_literals: bool) -> None:
        self.normalize_literals = normalize_literals

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # 保留既有候選基準的 0/1 邊界行為；near hash 只是篩選提示，不能當成語意等價。
        # Python 的 bool/int 相等性會讓 0/1 落入此分支，故報告明確揭露此侷限。
        if not self.normalize_literals or node.value in (None, True, False):
            return node
        return ast.copy_location(ast.Constant(value="__CONST__"), node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if not self.normalize_literals or node.id in {"self", "cls", "pytest", "mock", "patch"}:
            return node
        return ast.copy_location(ast.Name(id="__VAR__", ctx=node.ctx), node)


def normalize_nodes(nodes: Iterable[ast.AST], *, normalize_literals: bool) -> str:
    normalized = [copy.deepcopy(node) for node in nodes]
    normalized = [StructuralNormalizer(normalize_literals).visit(node) for node in normalized]
    module = ast.Module(body=[ast.fix_missing_locations(node) for node in normalized], type_ignores=[])
    return sha256(ast.dump(module, include_attributes=False).encode("utf-8")).hexdigest()


def normalize_exact(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return normalize_nodes(body, normalize_literals=False)


def normalize_near(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return normalize_nodes(body, normalize_literals=True)


def literal_values(node: ast.AST) -> list[str]:
    """Return compact literal evidence used for per-group contract comparison."""
    values: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Constant) or child.value is None or isinstance(child.value, bool):
            continue
        if isinstance(child.value, str) and len(child.value) > 120:
            value = repr(child.value[:117] + "...")
        else:
            value = repr(child.value)
        if value not in values:
            values.append(value)
    return values[:24]


def _assignment_target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assignment_target_names(element))
        return names
    return []


def _module_constant_summary(name: str, value: ast.AST) -> str:
    """Keep module-level test contract constants visible without dumping whole files."""
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        elements = [ast.unparse(element) for element in value.elts[:8]]
        suffix = "…" if len(value.elts) > 8 else ""
        return f"{name}={type(value).__name__}[{len(value.elts)}]:{','.join(elements)}{suffix}"
    if isinstance(value, ast.Dict):
        return f"{name}=dict[{len(value.keys)}]"
    text = ast.unparse(value).replace("\n", " ")
    return f"{name}={text[:180]}"


def module_constant_summaries(tree: ast.Module) -> list[str]:
    """Extract uppercase module assignments used as test input/coverage contracts."""
    summaries: list[str] = []
    for node in tree.body:
        assignments: list[tuple[list[str], ast.AST]] = []
        if isinstance(node, ast.Assign):
            assignments = [
                (name, node.value)
                for target in node.targets
                for name in [_assignment_target_names(target)]
                if name
            ]
        elif isinstance(node, ast.AnnAssign):
            names = _assignment_target_names(node.target)
            if node.value is not None and names:
                assignments = [(names, node.value)]
        for names, value in assignments:
            for name in names:
                if name.isupper():
                    summaries.append(_module_constant_summary(name, value))
    return sorted(set(summaries))


def module_metadata(tree: ast.Module) -> dict[str, Any]:
    imports: list[str] = []
    production_imports: list[str] = []
    module_helpers: list[str] = []
    module_fixtures: list[str] = []
    production_roots = {
        "analysis_module",
        "app_module",
        "backtest_module",
        "data_module",
        "decision_module",
        "development_module",
        "financial_module",
        "ml_module",
        "portfolio_module",
        "runtime",
        "ui_qt",
        "utils",
    }
    for node in tree.body:
        module = ""
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            module = node.names[0].name if node.names else ""
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.append(module)
        if module and module.lstrip(".").split(".", 1)[0] in production_roots:
            production_imports.append(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
            node.name.startswith("test_") or node.name.endswith("_test")
        ):
            module_helpers.append(node.name)
            if any(
                isinstance(decorator, ast.Attribute)
                and isinstance(decorator.value, ast.Name)
                and decorator.value.id == "pytest"
                and decorator.attr == "fixture"
                for decorator in node.decorator_list
            ) or any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "pytest"
                and decorator.func.attr == "fixture"
                for decorator in node.decorator_list
            ):
                module_fixtures.append(node.name)
    return {
        "module_imports": sorted(set(imports)),
        "production_imports": sorted(set(production_imports)),
        "module_helpers": sorted(set(module_helpers)),
        "module_fixtures": sorted(set(module_fixtures)),
        "module_constants": module_constant_summaries(tree),
    }


def relative_files(root: Path, pattern: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.glob(pattern) if path.is_file())


def extract_functions(discovery_files: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    functions: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    for rel_path in discovery_files:
        path = REPO_ROOT / rel_path
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            parse_errors.append(f"{rel_path}: {exc}")
            continue
        visitor = TestFunctionVisitor(rel_path, module_metadata(tree))
        visitor.visit(tree)
        functions.extend(visitor.functions)
    return functions, parse_errors


def population_metrics() -> dict[str, Any]:
    tests_dir = REPO_ROOT / "tests"
    scripts_dir = REPO_ROOT / "scripts"
    docs_qa_dir = REPO_ROOT / "docs" / "06_qa"
    all_tests = sorted(path.relative_to(REPO_ROOT).as_posix() for path in tests_dir.rglob("*.py"))
    manual = [path for path in all_tests if path.startswith(MANUAL_PREFIX)]
    internal = [path for path in all_tests if path.startswith(INTERNAL_PREFIX)]
    fixtures = [path for path in all_tests if path not in manual and path not in internal and not Path(path).name.startswith("test_")]
    discovery = [path for path in all_tests if Path(path).name.startswith("test_") and path not in manual and path not in internal]
    qa_scripts = relative_files(REPO_ROOT, "scripts/qa_*.py")
    validate_scripts = relative_files(REPO_ROOT, "scripts/validate_*.py")
    runtime_tests = relative_files(REPO_ROOT, "runtime/tests/*.py") if (REPO_ROOT / "runtime/tests").exists() else []
    executable = sorted(set(all_tests + qa_scripts + validate_scripts + runtime_tests))
    qa_docs = relative_files(REPO_ROOT, "docs/06_qa/*.md") if docs_qa_dir.exists() else []
    test_data: list[str] = []
    test_data_dir = REPO_ROOT / "tests/test_data"
    if test_data_dir.exists():
        for extension in ("*.json", "*.sqlite", "*.csv", "*.bin", "*.parquet"):
            test_data.extend(path.relative_to(REPO_ROOT).as_posix() for path in test_data_dir.rglob(extension))
    bounded = sorted(set(executable + qa_docs + test_data + ["pytest.ini"]))
    return {
        "scope_status": "bounded_path_union_only",
        "scope_warning": "固定路徑集合是 bounded union，不是全專案 QA 母體；本工具不宣稱 full_population_count。",
        "bounded_scope_assets": {
            "count": len(bounded),
            "included_roots": [
                "tests/**/*.py",
                "scripts/qa_*.py",
                "scripts/validate_*.py",
                "runtime/tests/*.py",
                "docs/06_qa/*.md",
                "tests/test_data/* (限定 json/sqlite/csv/bin/parquet)",
                "pytest.ini",
            ],
            "breakdown": {
                "tests_python": len(all_tests),
                "scripts_qa": len(qa_scripts),
                "scripts_validate": len(validate_scripts),
                "runtime_tests": len(runtime_tests),
                "docs_qa_md": len(qa_docs),
                "test_data_files": len(test_data),
                "pytest_ini": 1,
            },
        },
        "pytest_discovery_candidates": {
            "count": len(discovery),
            "definition": "tests/ 下檔名為 test_*.py，排除 manual/ 與 scripts/；這是 AST 探索範圍，不是 pytest collection 結果。",
        },
        "tests_python_total": {
            "count": len(all_tests),
            "breakdown": {
                "discovery_candidates": len(discovery),
                "manual_checks": len(manual),
                "internal_scripts": len(internal),
                "fixtures_and_conftest": len(fixtures),
            },
        },
        "full_population_count": None,
        "full_population_status": "not_established",
        "excluded_from_bounded_scope": [
            "其他 scripts/*.py（不符合 qa_*.py 或 validate_*.py）",
            "docs/ 下除 docs/06_qa/*.md 之外的文件",
            "runtime/ 下除 runtime/tests/*.py 之外的文件",
            "tests/ 下非 Python 檔與 tests/test_data 之外的測試資產",
            "output/、graphify-out/、.venv/ 等本機輸出／快取",
        ],
    }


def short_names(functions: list[dict[str, Any]], limit: int = 4) -> str:
    names = [f["qual_name"] for f in functions]
    shown = names[:limit]
    suffix = f"；另 {len(names) - limit} 個成員" if len(names) > limit else ""
    return "、".join(shown) + suffix


def evidence_locations(functions: list[dict[str, Any]]) -> str:
    return "; ".join(f"{f['rel_path']}:L{f['start_line']}-{f['end_line']}" for f in functions)


def functions_by_file(functions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for function in functions:
        grouped[function["rel_path"]].append(function)
    return grouped


def contract_summary(function: dict[str, Any]) -> str:
    """Summarise source-level contract evidence for one test member."""
    decorators = ",".join(function["decorators"]) or "無"
    fixtures = ",".join(function["fixture_dependencies"]) or "無"
    raises = ",".join(function["raises_contexts"][:2]) or "無"
    imports = ",".join(function["production_imports"][:4]) or "無"
    module_constants = ",".join(function["module_constants"][:4]) or "無"
    calls = ",".join(function["calls"][:6]) or "無"
    literals = ",".join(function["literal_values"][:6]) or "無"
    return (
        f"{function['qual_name']}〔fixture={fixtures}; decorator={decorators}; raises={raises}; "
        f"production_import={imports}; module_constants={module_constants}; calls={calls}; literals={literals}; "
        f"assertions={function['assertion_count']}〕"
    )


def contract_fingerprint(function: dict[str, Any]) -> str:
    """Fingerprint parsed contract fields without treating them as semantic proof."""
    payload = {
        "fixtures": function["fixture_dependencies"],
        "decorators": function["decorators"],
        "raises": function["raises_contexts"],
        "production_imports": function["production_imports"],
        "module_constants": function["module_constants"],
        "calls": function["calls"],
        "literals": function["literal_values"],
        "assertions": function["assertions"],
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def compact_contract_summary(function: dict[str, Any]) -> str:
    """Keep row-level evidence readable while retaining concrete source distinctions."""
    decorators = ",".join(function["decorators"]) or "無"
    fixtures = ",".join(function["fixture_dependencies"]) or "無"
    raises = ",".join(function["raises_contexts"][:2]) or "無"
    imports = ",".join(function["production_imports"][:3]) or "無"
    module_constants = ",".join(function["module_constants"][:3]) or "無"
    calls = ",".join(function["calls"][:5]) or "無"
    literals = ",".join(function["literal_values"][:4]) or "無"
    return (
        f"{function['qual_name']}〔fixture={fixtures}; decorator={decorators}; raises={raises}; "
        f"import={imports}; module_constants={module_constants}; calls={calls}; literals={literals}; "
        f"assert={function['assertion_count']}〕"
    )


def feature_for(function: dict[str, Any]) -> str | None:
    path = function["rel_path"].lower()
    name = function["qual_name"].lower()
    if "personalization" in path or "personalization" in name:
        return "Personalization"
    if "banktaiwan" in path or "banktaiwan" in name:
        return "BankTaiwanCostScenario"
    if "recommendation" in path and "learning" in path:
        return "RecommendationDailyLearning"
    if "official_market_event" in path or "market_event" in path:
        return "OfficialMarketEventCustody"
    if "mops" in path and "statement" in path:
        return "MOPSStatementCandidate"
    if "update_view" in path or "update_tab" in path or "update_service" in path:
        return "UpdateWorkbenchFlow"
    if "decision_continuity" in path or "continuity_review" in path:
        return "DecisionContinuityJourney"
    if "position_health" in path:
        return "PositionHealthProjection"
    return None


def layer_for(function: dict[str, Any]) -> str:
    path = function["rel_path"].lower()
    name = function["qual_name"].lower()
    if path.startswith("scripts/qa_validate") or "ui_" in path:
        return "UI / End-to-End"
    if "_cli" in path or "_cli" in name:
        return "CLI / Process"
    if "service" in path or "orchestration" in path or "loop" in path:
        return "Service / Integration"
    return "Unit / Contract"


def candidate_row(
    *,
    group_id: str,
    category: str,
    members: list[dict[str, Any]],
    member_source: str,
    review_status: str,
    inspected_scope: str,
    differences: str,
    evidence: str,
    disposition: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "category": category,
        "member_count": len(members),
        "members": "\n".join(member["member_id"] for member in members),
        "member_inventory_source": member_source,
        "semantic_review_status": review_status,
        "inspected_scope": inspected_scope,
        "differences": differences,
        "evidence_location": evidence,
        "disposition": disposition,
        "rationale": rationale,
    }


def build_candidates(functions: list[dict[str, Any]], manual_files: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for function in functions:
        exact_groups[function["exact_hash"]].append(function)
    exact_members: set[str] = set()
    for digest, members in sorted(exact_groups.items()):
        if len(members) < 2:
            continue
        exact_members.update(member["member_id"] for member in members)
        group_id = f"DUP-A-{digest[:8]}"
        if "test_formal_registration_plan.py" in str(members) and "test_paper_execution_registration_plan.py" in str(members):
            diff = "兩個成員指向不同排程註冊腳本；相同 AST 不代表相同入口。"
            rationale = f"{group_id} 保留兩個入口測試，因成員分別綁定 Formal 與 Paper 腳本；抽跨檔 helper 仍須另行驗證時區拒絕邊界。"
        elif "test_evidence_rehearsal_dtos.py" in str(members):
            diff = "兩個成員位於同檔但參數化情境分別是 production-like 欄位與 evidence filename 變形。"
            rationale = f"{group_id} 保留函式分立，使 CI 可直接區分欄位拒絕與路徑拒絕；目前沒有必要整併的回歸證據。"
        else:
            diff = "兩個成員雖有相同 AST，函式名稱與測試輸入仍代表不同邊界契約。"
            rationale = f"{group_id} 保留原寫法；現有 AST 證據不足以證明合併後失敗定位與契約標示等價。"
        rows.append(
            candidate_row(
                group_id=group_id,
                category="Category A (完全同構候選)",
                members=members,
                member_source="source AST exact hash",
                review_status="已完成候選範圍核對",
                inspected_scope="完整 AST、函式名稱、裝飾器／輸入與斷言邊界",
                differences=diff,
                evidence=evidence_locations(members),
                disposition="保留原寫法並說明",
                rationale=rationale,
            )
        )

    near_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for function in functions:
        if function["near_hash"] and function["line_count"] >= 4 and function["member_id"] not in exact_members:
            near_groups[function["near_hash"]].append(function)
    for digest, members in sorted(near_groups.items()):
        if len(members) < 2:
            continue
        group_id = f"DUP-B-{digest[:8]}"
        paths = sorted({member["rel_path"] for member in members})
        boundaries = [member["qual_name"] for member in members if member["is_boundary"]]
        call_sets = [set(member["calls"]) for member in members]
        shared_calls = sorted(set.intersection(*call_sets)) if call_sets else []
        unique_calls = sorted(set.union(*call_sets) - set(shared_calls)) if call_sets else []
        production_imports = sorted({item for member in members for item in member["production_imports"]})
        contract_fingerprints = {contract_fingerprint(member) for member in members}
        contract_summaries = "；".join(compact_contract_summary(member) for member in members)
        module_constants = sorted({item for member in members for item in member["module_constants"]})
        path_text = "、".join(paths)
        boundary_text = "、".join(boundaries[:3]) if boundaries else "函式名稱未含邊界標記"
        diff = (
            f"{len(paths)} 個檔案（{path_text}）；成員為 {short_names(members)}；"
            f"assert 數 {[member['assertion_count'] for member in members]}；"
            f"共同呼叫 {shared_calls[:4] or '無'}，差異呼叫 {unique_calls[:4] or '無'}；"
            f"production import={production_imports or '無'}；邊界成員：{boundary_text}；"
            f"module constants={module_constants or '無'}；"
            f"逐成員契約={contract_summaries}。"
        )
        if len(contract_fingerprints) == 1:
            contract_note = (
                "所有成員在本次解析的 decorator、fixture、raises、production import、module-level constants、"
                "literal、call 與 assertion 欄位相同；near-hash 候選沒有提供可直接參數化的契約差異。"
                f"保留各自的檔案／函式 identity（{path_text}；{short_names(members)}），"
                "以維持失敗定位與測試命名，不能把相同指紋解讀成語意等價。"
            )
        else:
            contract_note = (
                f"解析欄位形成 {len(contract_fingerprints)} 個契約指紋；可見差異為 "
                f"production import={production_imports or '無'}、共同呼叫={shared_calls[:3] or '無'}、"
                f"差異呼叫={unique_calls[:3] or '無'}、boundary={boundary_text}、"
                f"module constants={module_constants or '無'}。"
                "這些 source-level 差異仍需動態驗證，不能把指紋差異解讀成語意等價。"
            )
        rationale = (
            f"{group_id} 已逐一解析 {len(members)} 個完整函式的 decorator、fixture 參數、raises、production import、"
            f"literal 與 assert；契約指紋數={len(contract_fingerprints)}。"
            f"{contract_note}"
            "本次不變更測試，收益記為零，僅未執行動態回歸。"
        )
        rows.append(
            candidate_row(
                group_id=group_id,
                category="Category B (結構同構常數差異候選)",
                members=members,
                member_source="source AST near hash after Category A exclusion",
                review_status="已完成靜態契約／fixture／import 查核；未動態回歸",
                inspected_scope="near-hash AST、完整 source/decorator/import/fixture/raises/assert 解析；未執行動態回歸",
                differences=diff,
                evidence=evidence_locations(members),
                disposition="保留原寫法並說明",
                rationale=rationale,
            )
        )

    by_file = functions_by_file(functions)
    c_index = 1
    c_rows: list[dict[str, Any]] = []
    for path, file_functions in sorted(by_file.items()):
        if len(file_functions) < 5:
            continue
        heavy = [function for function in file_functions if function["setup_line_count"] >= 10]
        if len(heavy) < 4:
            continue
        average_setup = sum(function["setup_line_count"] for function in heavy) // len(heavy)
        estimated_savings = (len(heavy) - 1) * (average_setup - 2)
        if estimated_savings < 30:
            continue
        group_id = f"DUP-C-{c_index:03d}"
        c_index += 1
        if group_id in REVIEWED_C_PATHS and REVIEWED_C_PATHS[group_id] != path:
            raise ValueError(
                f"候選基準已位移：{group_id} 對應 {path}；"
                "請重新審閱並更新歷史路徑對照，不可沿用舊處置。"
            )
        setup_sets = [set(function["setup_calls"]) for function in heavy]
        shared_setup = sorted(set.intersection(*setup_sets)) if setup_sets else []
        setup_shapes = Counter(function["setup_hash"] for function in heavy)
        setup_exact_shapes = Counter(function["setup_exact_hash"] for function in heavy)
        contract_fingerprints = {contract_fingerprint(function) for function in heavy}
        distinct_boundary = [function["qual_name"] for function in heavy if function["is_boundary"]]
        source_imports = sorted({item for function in heavy for item in function["production_imports"]})
        source_helpers = sorted({item for function in heavy for item in function["module_helpers"]})
        fixture_args = sorted({item for function in heavy for item in function["fixture_dependencies"]})
        member_contracts = "；".join(compact_contract_summary(function) for function in heavy)
        if group_id == "DUP-C-025":
            review_status = "已完成逐行核對與 focused 回歸"
            disposition = "已整併"
            differences = (
                f"AST setup 分群有 {len(heavy)} 個測試成員；其中既有 commit 已核對 10 處 HTTP response 定義，"
                f"7 處為純樣板、3 處保留 read(limit)／特殊 header 防禦契約；"
                f"exact setup shape={len(setup_exact_shapes)}、normalized shape={len(setup_shapes)}；"
                f"production import={source_imports or '無'}；module helper={source_helpers or '無'}。"
            )
            rationale = (
                f"{group_id} 的可整併範圍限於 7 處純 HTTP response 樣板；3 處含讀取上限或特殊 header，已留在原位。"
                f"目前 AST heavy 成員={len(heavy)}、exact setup shape={len(setup_exact_shapes)}、"
                f"normalized shape={len(setup_shapes)}、逐成員契約指紋={len(contract_fingerprints)}；"
                "既有 focused suite 需維持 18 個 node identity，故不以 setup 群組數宣稱所有測試可合併。"
            )
        elif group_id in TOP_C_REVIEWED:
            review_status = "已完成靜態契約／fixture／setup 查核；未動態回歸"
            disposition = "保留原寫法並說明"
            differences = (
                f"{len(heavy)} 個成員位於 {path}；setup 行數範圍 "
                f"{min(function['setup_line_count'] for function in heavy)}–{max(function['setup_line_count'] for function in heavy)}；"
                f"共同 setup 呼叫 {shared_setup[:6] or '無'}；exact setup shape {len(setup_exact_shapes)}、"
                f"normalized shape {len(setup_shapes)}；fixture 參數={fixture_args or '無'}；"
                f"production import={source_imports or '無'}；邊界成員 {distinct_boundary[:3] or '無'}；"
                f"逐成員契約={member_contracts}。"
            )
            if len(setup_exact_shapes) == 1:
                setup_reason = (
                    "exact setup shape 全部相同，但逐成員 decorator／fixture／raises／import／literal／"
                    "assert 契約仍須與函式 body 一起維持；setup 相同不代表整個測試語意相同。"
                )
            else:
                setup_reason = (
                    f"exact setup shape 有 {len(setup_exact_shapes)} 種，需保留 setup AST 的實際差異；"
                    "normalized shape 也只作整理線索。"
                )
            rationale = (
                f"{group_id} 已逐一解析 {path} 的 decorator、fixture 參數、raises、production import、literal、"
                f"assert 與 setup AST；{len(setup_exact_shapes)} 個 exact setup shape／{len(setup_shapes)} 個 normalized shape，"
                f"逐成員契約指紋={len(contract_fingerprints)}、共同 setup={shared_setup[:4] or '無'}、"
                f"module helper={source_helpers or '無'}。{setup_reason}"
                "完整成員契約摘要與行號列於差異欄；本次保留原寫法，收益為零，未執行動態回歸。"
            )
        else:
            review_status = "已完成靜態契約／fixture／setup 查核；未動態回歸"
            disposition = "保留原寫法並說明"
            differences = (
                f"{len(heavy)} 個成員位於 {path}；setup 行數範圍 "
                f"{min(function['setup_line_count'] for function in heavy)}–{max(function['setup_line_count'] for function in heavy)}；"
                f"共同 setup 呼叫 {shared_setup[:5] or '無'}；exact setup shape {len(setup_exact_shapes)} 種、"
                f"normalized shape {len(setup_shapes)} 種；fixture 參數={fixture_args or '無'}；"
                f"production import={source_imports or '無'}；boundary 成員 {distinct_boundary[:3] or '無'}；"
                f"逐成員契約={member_contracts}。"
            )
            if len(setup_exact_shapes) == 1:
                setup_reason = (
                    "exact setup shape 全部相同，但各成員的 decorator／fixture／raises／import／literal／"
                    "assert 與函式 body 仍須個別保留；setup 重複不足以證明可安全抽 fixture。"
                )
            else:
                setup_reason = (
                    f"exact setup shape 有 {len(setup_exact_shapes)} 種、normalized shape 有 {len(setup_shapes)} 種，"
                    "setup AST 仍存在個別差異，不能只依 heavy count 合併。"
                )
            rationale = (
                f"{group_id} 已逐一解析 {path} 的 {len(heavy)} 個成員（{short_names(heavy, 3)}）之 decorator、fixture、"
                f"raises、production import、literal、assert 與 setup AST；exact setup shape={len(setup_exact_shapes)}、"
                f"normalized shape={len(setup_shapes)}、逐成員契約指紋={len(contract_fingerprints)}、"
                f"共同 setup={shared_setup[:3] or '無'}、module helper={source_helpers or '無'}。{setup_reason}"
                "完整成員契約摘要與行號列於差異欄；保留原寫法，收益為零，未執行動態回歸。"
            )
        c_rows.append(
            candidate_row(
                group_id=group_id,
                category="Category C (重複Setup候選)",
                members=heavy,
                member_source="source AST heavy-setup predicate (setup_line_count >= 10)",
                review_status=review_status,
                inspected_scope="測試函式成員、setup 行數、setup call／shape 與 boundary 名稱摘要",
                differences=differences,
                evidence=evidence_locations(heavy),
                disposition=disposition,
                rationale=rationale,
            )
        )
    rows.extend(c_rows)

    feature_clusters: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for function in functions:
        feature = feature_for(function)
        if feature:
            feature_clusters[feature][layer_for(function)].append(function)
    d_index = 1
    for feature, layers in feature_clusters.items():
        if len(layers) < 3:
            continue
        members = [member for layer_members in layers.values() for member in layer_members]
        group_id = f"DUP-D-{d_index:03d}"
        d_index += 1
        layer_summary = ", ".join(f"{layer}={len(layer_members)}" for layer, layer_members in layers.items())
        rows.append(
            candidate_row(
                group_id=group_id,
                category="Category D (多層驗證)",
                members=members,
                member_source="source AST feature and layer classifier",
                review_status="已完成架構邊界核對；非重複刪除授權",
                inspected_scope="完整 feature cluster 成員、架構層級與測試入口分類",
                differences=f"{feature} 分布於 {layer_summary}；層級入口與故障模式不同。",
                evidence=evidence_locations(members),
                disposition="已全面撤回",
                rationale=(
                    f"{group_id} 的 {feature} 只是跨層驗證群組（{layer_summary}），不是可由 AST 相似推導的代碼重複。"
                    "保留 Unit／Service／CLI／UI 的縱深防禦，估算收益撤回為零。"
                ),
            )
        )

    for index, rel_path in enumerate(manual_files, start=1):
        path = REPO_ROOT / rel_path
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(content, filename=str(path))
        assertion_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
        if path.name == "legacy_api_endpoints_check.py":
            subtype = "獨立端點連線探測"
            diff = "檔案含外部 HTTP／urllib 連線探測，但本次工具不執行該腳本。"
        elif assertion_count:
            subtype = "舊斷言相容性檢查"
            diff = f"檔案含 {assertion_count} 個 assert；屬 manual-only，不能以未執行推論現代替代已通過。"
        else:
            subtype = "純 print 歷史觀察"
            diff = "檔案沒有 assert，主要輸出歷史演算法觀察結果。"
        rows.append(
            {
                "group_id": f"DUP-E-{index:03d}",
                "category": f"Category E (手動 Legacy：{subtype})",
                "member_count": 1,
                "members": rel_path,
                "member_inventory_source": "source file identity",
                "semantic_review_status": "已完成檔案特徵核對",
                "inspected_scope": "檔案存在性、AST assert 統計與文字型網路線索；未執行腳本",
                "differences": diff,
                "evidence_location": f"{rel_path}:L1-{len(content.splitlines())}",
                "disposition": "原位手動診斷保留",
                "rationale": f"{rel_path} 已由 pytest 排除；保留原位以維持歷史診斷入口，任何 archive 或刪除仍須另行授權與驗證。",
            }
        )
    return rows


def validate_rows(rows: list[dict[str, Any]], functions: list[dict[str, Any]], manual_files: list[str]) -> dict[str, Any]:
    function_ids = {function["member_id"] for function in functions}
    valid_manual = set(manual_files)
    errors: list[str] = []
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    disposition_review_ids: list[str] = []
    business_review_pending_ids: list[str] = []
    static_screened_ids: list[str] = []
    for row in rows:
        category_counts[row["category"]] += 1
        status_counts[row["semantic_review_status"]] += 1
        members = row["members"].splitlines() if row["members"] else []
        try:
            declared = int(row["member_count"])
        except (TypeError, ValueError):
            declared = -1
        if declared != len(members):
            errors.append(f"{row['group_id']}: member_count={declared}, members={len(members)}")
        if len(members) != len(set(members)):
            errors.append(f"{row['group_id']}: duplicate member identity")
        if any("..." in member for member in members):
            errors.append(f"{row['group_id']}: truncated member marker")
        if row["group_id"].startswith("DUP-E-"):
            if members != [member for member in members if member in valid_manual]:
                errors.append(f"{row['group_id']}: manual member path is not a current manual file")
        elif any(member not in function_ids for member in members):
            missing = [member for member in members if member not in function_ids]
            errors.append(f"{row['group_id']}: missing AST member {missing[:2]}")
        if "靜態契約" in row["semantic_review_status"]:
            static_screened_ids.append(row["group_id"])
        if row["group_id"].startswith("DUP-B-") or (
            row["group_id"].startswith("DUP-C-") and row["group_id"] not in TOP_C_REVIEWED
        ):
            business_review_pending_ids.append(row["group_id"])
        else:
            disposition_review_ids.append(row["group_id"])
    return {
        "candidate_row_count": len(rows),
        "category_counts": dict(category_counts),
        "member_inventory": {
            "rows_with_source_member_list": sum(1 for row in rows if row["members"]),
            "rows_count_matching_member_list": len(rows) - len(errors),
            "validation_errors": errors,
            "interpretation": "這是 identity inventory 檢查，不是 139 組均完成業務語意深審的證明。",
        },
        "semantic_review": {
            "static_contract_screened_group_count": len(static_screened_ids),
            "static_contract_screened_group_ids": static_screened_ids,
            "disposition_reviewed_group_count": len(disposition_review_ids),
            "disposition_reviewed_group_ids": disposition_review_ids,
            "business_review_pending_group_count": len(business_review_pending_ids),
            "business_review_pending_group_ids": business_review_pending_ids,
            "business_review_pending_scope": "Category B 69 組 + Category C 其餘 44 組；已完成靜態契約篩選，未做逐組動態回歸或深層語意驗證。",
        },
        "status_counts": dict(status_counts),
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "group_id",
        "category",
        "member_count",
        "members",
        "member_inventory_source",
        "semantic_review_status",
        "inspected_scope",
        "differences",
        "evidence_location",
        "disposition",
        "rationale",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(rows: list[dict[str, Any]], population: dict[str, Any], integrity: dict[str, Any], focused_result: str) -> str:
    def cell(value: str) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br/>")

    category_counts = Counter(row["category"] for row in rows)
    disposition_counts = Counter(row["disposition"] for row in rows)
    lines = [
        "# 測試資產整理與候選處置結案報告（證據邊界修正版）\n",
        "> **日期**：2026-09-17\n",
        "> **性質**：repository-only bounded QA audit；不修改 production、不讀取正式資料、不呼叫網路、不執行排程。本次子任務不執行 commit，由 root 統一提交。\n",
        "\n## 1. 判讀結論\n",
        "本次重建把候選成員清冊、檔案母體計數與業務語意審查分開記錄。139 組候選均列入清冊，但清冊 identity 檢查不等於 139 組均完成深層查核；Category B 69 組與 Category C 其餘 44 組已逐組完成靜態契約／fixture／import 篩選，保留原寫法並明確記錄尚未動態回歸的邊界。\n",
        "`DUP-C-025` 僅保留既有 commit 已證實的 7 處純 HTTP response 樣板整併；其餘 4 組 Top C 候選完成隔離性核對後保留原寫法。Category D 的跨層候選全部撤回整併收益。\n",
        "\n## 2. 母體口徑：bounded union 的固定範圍與限制\n",
        f"本次掃描得到明確納入路徑的 bounded union **{population['bounded_scope_assets']['count']} 檔**。它由固定路徑集合組成，沒有對 repository 建立全域 QA taxonomy，因此 `full_population_count` 維持 `null`，不宣稱這個 bounded union 是完整母體。\n",
        "舊口徑所稱「73 檔差集已確認暫存快照」沒有可重建的舊名單或 hash manifest；本次明確撤回該宣稱，不把 73 檔納入 inventory 或驗證結論。\n",
        "\n| 子集合 | 數量 | 定義 |\n|---|---:|---|\n",
        f"| tests Python | {population['bounded_scope_assets']['breakdown']['tests_python']} | `tests/**/*.py` |\n",
        f"| scripts QA | {population['bounded_scope_assets']['breakdown']['scripts_qa']} | `scripts/qa_*.py` |\n",
        f"| scripts validate | {population['bounded_scope_assets']['breakdown']['scripts_validate']} | `scripts/validate_*.py` |\n",
        f"| runtime tests | {population['bounded_scope_assets']['breakdown']['runtime_tests']} | `runtime/tests/*.py` |\n",
        f"| QA Markdown | {population['bounded_scope_assets']['breakdown']['docs_qa_md']} | `docs/06_qa/*.md` |\n",
        f"| test data | {population['bounded_scope_assets']['breakdown']['test_data_files']} | `tests/test_data` 限定副檔名 |\n",
        "| pytest.ini | 1 | 明確納入的設定檔 |\n",
        "\n排除範圍包括其他 `scripts/*.py`、其他 `docs/`、其他 `runtime/`、非 Python 測試資產與本機輸出／快取。這些排除項沒有被估算成「不存在」，只是未納入本 bounded union。\n",
        "\n## 3. 候選 identity 與審查狀態\n",
        "near-hash 僅作候選篩選：為維持既有 139 組基準，正規化沿用 `None/True/False` 保留分支，因此 Python `0 == False`、`1 == True` 的邊界會保留 0/1 常數；這不影響本次逐組 source contract 核對，也不能把 hash 當成語意等價證據。\n",
        f"清冊共有 **{integrity['candidate_row_count']} 組**；identity inventory 錯誤數為 **{len(integrity['member_inventory']['validation_errors'])}**。這表示每列的 `member_count` 與列出的 member identity 可相互核對，不代表每列已完成業務語意 review。\n",
        f"完成明確處置核對的候選為 {integrity['semantic_review']['disposition_reviewed_group_count']} 組；另有 {integrity['semantic_review']['business_review_pending_group_count']} 組已完成靜態契約／fixture／import 篩選但仍待動態回歸與深層語意驗證，範圍是 B 69 組 + C 44 組。\n",
        "\n| 類別 | 組數 | 處置摘要 |\n|---|---:|---|\n",
        f"| Category A | {category_counts['Category A (完全同構候選)']} | 保留原寫法並說明 |\n",
        f"| Category B | {category_counts['Category B (結構同構常數差異候選)']} | 全數完成靜態契約篩選後保留；未動態回歸 |\n",
        f"| Category C | {category_counts['Category C (重複Setup候選)']} | 1 組已整併；4 組靜態核對後保留；44 組靜態篩選後保留 |\n",
        f"| Category D | {category_counts['Category D (多層驗證)']} | 全數撤回整併收益 |\n",
        f"| Category E | {sum(count for category, count in category_counts.items() if category.startswith('Category E'))} | 原位手動診斷保留 |\n",
        "\n處置計數：" + "、".join(f"{name}={count}" for name, count in sorted(disposition_counts.items())) + "。\n",
        "\n## 4. Focused 驗證\n",
        f"{focused_result}\n",
        "Reviewer 獨立重跑 audit CLI 成功；另驗證 AST 正規化不修改原樹、模組常數擷取及錯誤成員清單拒絕。C 類歷史處置另外核對檔案路徑，流水號位移時停止，避免套用錯誤結論。\n",
        "審計 CLI 本身只做 AST／檔案結構分析；本次不執行 manual-only 腳本、不執行真實 HTTP、不讀取 DATA_ROOT、不執行 scheduler。\n",
        "\n## 5. 139 組逐列清冊\n",
        "下表的成員列是完整 identity inventory；`semantic_review_status` 明確區分靜態契約／fixture／import 篩選與仍未動態回歸的邊界。113 組 B/C 保留列均含該組自己的檔案、函式、setup AST、decorator、fixture、import、literal、raises 或 assertion 證據，不以共同樣板宣稱已完成全域深審。\n",
        "\n| Group ID | 類別 | 成員數 | 成員 identity | inventory 來源 | 語意審查狀態 | 差異與證據 | 處置 | 理由 |\n|---|---|---:|---|---|---|---|---|---|\n",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{cell(row['group_id'])}`",
                    cell(row["category"]),
                    str(row["member_count"]),
                    cell(row["members"]),
                    cell(row["member_inventory_source"]),
                    cell(row["semantic_review_status"]),
                    cell(row["differences"] + "；證據：" + row["evidence_location"]),
                    cell(row["disposition"]),
                    cell(row["rationale"]),
                ]
            )
            + " |\n"
        )
    lines.extend(
        [
            "\n## 6. 後續邊界\n",
            "113 組 B/C 候選已完成靜態候選處置，目前依證據保留原狀且未計入整併收益；若未來要整併，須一次一檔建立 before/after diff，保留所有 boundary／failure injection，執行該檔 focused suite 後再獨立提交。\n",
            "完整原始 CSV／JSON 仍是 `output/qa/test_asset_audit/` 的本機產出；可重跑工具為 `scripts/audit_test_asset_consolidation.py`。\n",
        ]
    )
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--render-doc", action="store_true")
    parser.add_argument("--focused-result", default="未由 audit CLI 執行 focused pytest；請在報告中補入實際命令與結果。")
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    population = population_metrics()
    discovery_files = sorted(
        item.relative_to(REPO_ROOT).as_posix()
        for item in (REPO_ROOT / "tests").rglob("test_*.py")
        if "manual" not in item.parts and "scripts" not in item.parts
    )
    functions, parse_errors = extract_functions(discovery_files)
    manual_files = relative_files(REPO_ROOT, "tests/manual/legacy_*_check.py")
    rows = build_candidates(functions, manual_files)
    integrity = validate_rows(rows, functions, manual_files)
    integrity["parse_errors"] = parse_errors
    if parse_errors or integrity["member_inventory"]["validation_errors"]:
        raise SystemExit(json.dumps(integrity, ensure_ascii=False, indent=2))

    (output_dir / "population_metrics_v4.json").write_text(json.dumps(population, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "candidate_integrity_v4.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(rows, output_dir / "candidate_dispositions_detailed_v4.csv")
    # Keep the conventional local artifact name available for existing readers.
    write_csv(rows, output_dir / "candidate_dispositions_detailed.csv")
    if args.render_doc:
        doc_path = REPO_ROOT / "docs/06_qa/TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md"
        doc_path.write_text(render_markdown(rows, population, integrity, args.focused_result), encoding="utf-8")

    print(json.dumps({
        "output_dir": output_dir.as_posix(),
        "test_files": len(discovery_files),
        "ast_functions": len(functions),
        "candidate_rows": len(rows),
        "business_review_pending": integrity["semantic_review"]["business_review_pending_group_count"],
        "bounded_scope_assets": population["bounded_scope_assets"]["count"],
        "rendered_doc": bool(args.render_doc),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
