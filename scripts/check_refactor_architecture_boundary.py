"""R030 的有限架構邊界檢查。"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BoundaryDiagnostic:
    rule: str
    path: str
    line: int
    detail: str

    def render(self) -> str:
        return f"{self.rule}:{self.path}:{self.line}: {self.detail}"


def _python_files(root: Path, relative: str) -> tuple[Path, ...]:
    directory = root / relative
    if not directory.exists():
        return ()
    return tuple(sorted(directory.rglob("*.py")))


def _read_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_app_module(name: str | None) -> bool:
    return name == "app_module" or bool(name and name.startswith("app_module."))


def _decision_import_diagnostics(root: Path) -> list[BoundaryDiagnostic]:
    findings: list[BoundaryDiagnostic] = []
    for path in _python_files(root, "decision_module"):
        tree = _read_tree(path)
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            for module in imported:
                if _is_app_module(module):
                    findings.append(
                        BoundaryDiagnostic(
                            "decision_imports_app",
                            _relative(root, path),
                            getattr(node, "lineno", 0),
                            f"decision 層不可依賴 {module}",
                        )
                    )
    return findings


def _duplicate_row_map_diagnostics(root: Path) -> list[BoundaryDiagnostic]:
    """拒絕 execute/save/replay 再手工拼一份 canonical decision row。"""

    protected_paths = {
        "app_module/recommendation/execute.py",
        "app_module/recommendation/persistence.py",
        "app_module/recommendation_replay_service.py",
    }
    findings: list[BoundaryDiagnostic] = []
    for relative in sorted(protected_paths):
        path = root / relative
        if not path.exists():
            continue
        tree = _read_tree(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "RecommendationItem"
            ):
                findings.append(
                    BoundaryDiagnostic(
                        "duplicate_row_map",
                        relative,
                        node.lineno,
                        "execute/save/replay 不得從欄位逐項重建 canonical RecommendationItem",
                    )
                )
    return findings


def _business_last_state_diagnostics(root: Path) -> list[BoundaryDiagnostic]:
    paths = (
        root / "app_module/recommendation/persistence.py",
        root / "app_module/recommendation/queries.py",
        *_python_files(root, "ui_qt/views/recommendation"),
    )
    findings: list[BoundaryDiagnostic] = []
    for path in paths:
        if not path.exists():
            continue
        tree = _read_tree(path)
        for node in ast.walk(tree):
            receiver = ast.unparse(node.value) if isinstance(node, ast.Attribute) else ""
            receiver_is_business_service = "service" in receiver.lower()
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and node.attr.startswith("last_")
                and receiver_is_business_service
            ):
                findings.append(
                    BoundaryDiagnostic(
                        "business_last_state_read",
                        _relative(root, path),
                        node.lineno,
                        f"讀取 {node.attr!r}；保存、query 與呈現只能使用本次 execution/read model",
                    )
                )
    return findings


def _strategy_registry_diagnostics(root: Path) -> list[BoundaryDiagnostic]:
    path = root / "app_module/backtest_service.py"
    if not path.exists():
        return []
    tree = _read_tree(path)
    imports_registry = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "decision_module.strategies.registry"
        and any(alias.name == "StrategyRegistry" for alias in node.names)
        for node in ast.walk(tree)
    )
    calls_registry = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_executor"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "StrategyRegistry"
        for node in ast.walk(tree)
    )
    strategy_id_branch = any(
        isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Attribute) and child.attr == "strategy_id"
            for child in ast.walk(node.test)
        )
        for node in ast.walk(tree)
    )
    if imports_registry and calls_registry and not strategy_id_branch:
        return []
    return [
        BoundaryDiagnostic(
            "strategy_registry_bypass",
            _relative(root, path),
            1,
            "backtest strategy resolution must use StrategyRegistry.get_executor without a strategy_id branch",
        )
    ]


def inspect_root(root: Path) -> tuple[BoundaryDiagnostic, ...]:
    resolved_root = root.resolve()
    findings = (
        _decision_import_diagnostics(resolved_root)
        + _duplicate_row_map_diagnostics(resolved_root)
        + _business_last_state_diagnostics(resolved_root)
        + _strategy_registry_diagnostics(resolved_root)
    )
    return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.rule)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args(argv)
    findings = inspect_root(args.root)
    if findings:
        print("\n".join(item.render() for item in findings))
        return 1
    print("R030 architecture boundary: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
