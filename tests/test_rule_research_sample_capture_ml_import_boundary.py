"""驗證技術 parent 查詢匯入不會預先載入 ML 套件，並保留 legacy capture 契約。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_public_technical_parent_query_import_does_not_load_ml_module_in_fresh_process() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = "\n".join(
        (
            "import json, sys",
            "from pathlib import Path",
            "from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalRuleStateFilterV4",
            "from app_module.daily_market_technical_universe_v4_producer import DailyMarketTechnicalUniverseV4ProductionRequest, produce_daily_market_technical_universe_v4",
            "from app_module.daily_market_technical_universe_v4_query import open_daily_market_technical_universe_v4_read_session",
            "from app_module.daily_market_technical_universe_v4_store import DailyMarketTechnicalUniverseV4Cohort, DailyMarketTechnicalUniverseV4StoreReader",
            "from app_module.rule_research_sample_capture import ResearchCaptureWriteScope",
            "import app_module.daily_market_technical_parent_v4_query as query_module",
            "print(json.dumps({",
            "    'query_origin': str(Path(query_module.__file__).resolve()),",
            "    'symbol_name': DailyMarketTechnicalRuleStateFilterV4.__name__,",
            "    'api_names': [DailyMarketTechnicalUniverseV4ProductionRequest.__name__, produce_daily_market_technical_universe_v4.__name__, open_daily_market_technical_universe_v4_read_session.__name__, DailyMarketTechnicalUniverseV4Cohort.__name__, DailyMarketTechnicalUniverseV4StoreReader.__name__, ResearchCaptureWriteScope.__name__],",
            "    'ml_modules': sorted(name for name in sys.modules if name == 'ml_module' or name.startswith('ml_module.')),",
            "}, sort_keys=True))",
        )
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["query_origin"] == str(
        (repository_root / "app_module" / "daily_market_technical_parent_v4_query.py").resolve()
    )
    assert result["symbol_name"] == "DailyMarketTechnicalRuleStateFilterV4"
    assert result["api_names"] == [
        "DailyMarketTechnicalUniverseV4ProductionRequest",
        "produce_daily_market_technical_universe_v4",
        "open_daily_market_technical_universe_v4_read_session",
        "DailyMarketTechnicalUniverseV4Cohort",
        "DailyMarketTechnicalUniverseV4StoreReader",
        "ResearchCaptureWriteScope",
    ]
    assert result["ml_modules"] == []


def test_legacy_pinned_capture_readback_preserves_contract_semantics(tmp_path: Path) -> None:
    from app_module.rule_research_sample_capture import read_rule_research_capture
    from tests.test_rule_research_sample_capture import DECISION_DATE, PUBLISHED_AT, _fixture

    repository, snapshot, expected_capture = _fixture(tmp_path)
    actual_capture = read_rule_research_capture(
        repository,
        manifest_sha256=snapshot.manifest_sha256,
        cohort_id=snapshot.cohort_id,
        decision_date=DECISION_DATE,
        as_of=PUBLISHED_AT,
        observed_at=PUBLISHED_AT,
    )

    expected_body = expected_capture.to_dict()
    actual_body = actual_capture.to_dict()
    assert actual_body == expected_body
    assert actual_body["feature_contract_version"] == snapshot.manifest["feature_contract_version"]
    assert actual_body["method_contracts"] == snapshot.manifest["method_contracts"]
    assert actual_body["method_contracts_sha256"] == snapshot.manifest["method_contracts_sha256"]
