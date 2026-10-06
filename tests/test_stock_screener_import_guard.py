import ast
import inspect
import sqlite3
import subprocess
import sys
import textwrap


def test_stock_screener_import_has_no_concrete_reader_dependency() -> None:
    script = textwrap.dedent(
        """
        import sqlite3
        import sys

        def reject_connection(*args, **kwargs):
            raise AssertionError("decision import attempted a SQLite connection")

        sqlite3.connect = reject_connection
        import decision_module.stock_screener as stock_screener

        assert "decision_module.stock_screener_sqlite_reader" not in sys.modules
        assert "data_module.stock_screener_reader" not in sys.modules
        assert "data_module.db_manager" not in sys.modules
        assert not hasattr(stock_screener, "sqlite3")
        assert not hasattr(stock_screener, "Path")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    from decision_module import stock_screener

    source_path = inspect.getsourcefile(stock_screener)
    assert source_path is not None
    with open(source_path, encoding="utf-8") as source_file:
        tree = ast.parse(source_file.read())

    forbidden_modules = {
        "pathlib",
        "sqlite3",
        "data_module.stock_screener_reader",
        "data_module.db_manager",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_modules
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"read_csv", "execute_query", "glob", "exists"}
