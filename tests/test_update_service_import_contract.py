from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ALL = [
    "RecommendationService",
    "ScreeningService",
    "RegimeService",
    "UpdateService",
    "BacktestService",
    "PortfolioService",
    "JournalService",
    "RecommendationDTO",
    "RecommendationResultDTO",
    "RegimeResultDTO",
    "BacktestReportDTO",
]
EXPECTED_PUBLIC_SERVICE_MODULES = [
    "app_module.backtest_service",
    "app_module.journal_service",
    "app_module.portfolio_service",
    "app_module.recommendation_service",
    "app_module.regime_service",
    "app_module.screening_service",
    "app_module.update_service",
]
EXPECTED_LAZY_SERVICE_MODULES = ["app_module.update_service"]
EXPECTED_SERVICE_CLASS_MODULES = {
    "RecommendationService": "app_module.recommendation_service",
    "ScreeningService": "app_module.screening_service",
    "RegimeService": "app_module.regime_service",
    "UpdateService": "app_module.update_service",
    "BacktestService": "app_module.backtest_service",
    "PortfolioService": "app_module.portfolio_service",
    "JournalService": "app_module.journal_service",
}


def test_update_service_imports_normalization_as_an_explicit_submodule_dependency():
    source_path = REPOSITORY_ROOT / "app_module" / "update_service.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    package_attribute_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "app_module"
        and any(alias.name == "update_data_normalization" for alias in node.names)
    ]

    assert package_attribute_imports == []


def test_update_service_package_import_contract_is_stable_in_fresh_interpreter():
    witness_script = """
import json
import sys

try:
    import app_module.update_service as update_service
    import app_module
except Exception as exc:
    print(json.dumps({"exception": type(exc).__name__, "message": str(exc)}))
    raise

loaded_before_public_access = [
    name for name in sys.modules if name.startswith("app_module.")
]
service_class_modules = {
    class_name: getattr(app_module, class_name).__module__
    for class_name in [
        "RecommendationService",
        "ScreeningService",
        "RegimeService",
        "UpdateService",
        "BacktestService",
        "PortfolioService",
        "JournalService",
    ]
}
loaded_after_public_access = [
    name for name in sys.modules if name.startswith("app_module.")
]
print(
    json.dumps(
        {
            "update_service_module": update_service.UpdateService.__module__,
            "identity": app_module.UpdateService is update_service.UpdateService,
            "all": list(app_module.__all__),
            "loaded_service_modules_before_public_access": [
                name
                for name in loaded_before_public_access
                if name in {
                    "app_module.recommendation_service",
                    "app_module.screening_service",
                    "app_module.regime_service",
                    "app_module.update_service",
                    "app_module.backtest_service",
                    "app_module.portfolio_service",
                    "app_module.journal_service",
                }
            ],
            "loaded_service_modules_after_public_access": [
                name
                for name in sorted(loaded_after_public_access)
                if name in {
                    "app_module.recommendation_service",
                    "app_module.screening_service",
                    "app_module.regime_service",
                    "app_module.update_service",
                    "app_module.backtest_service",
                    "app_module.portfolio_service",
                    "app_module.journal_service",
                }
            ],
            "service_class_modules": service_class_modules,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
)
"""

    result = subprocess.run(
        [sys.executable, "-c", witness_script],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "update_service_module": "app_module.update_service",
        "identity": True,
        "all": EXPECTED_ALL,
        "loaded_service_modules_before_public_access": EXPECTED_LAZY_SERVICE_MODULES,
        "loaded_service_modules_after_public_access": EXPECTED_PUBLIC_SERVICE_MODULES,
        "service_class_modules": EXPECTED_SERVICE_CLASS_MODULES,
    }
