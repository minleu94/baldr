"""策略 Health 命令沿原組裝與原 evaluator 寫衍生版本，不動帳本。"""

import json
import shutil

import pytest

from app_module.portfolio_research_initial_source import PortfolioResearchInitialSourceProvider
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService
from scripts.run_strategy_position_health import main
from test_position_health_strategy_archive import _prepared_pipeline, _write_strategy_governed_sources


def test_cli_publishes_real_pair_from_existing_strategy_and_governed_sources(tmp_path, monkeypatch, capsys):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    sources = _write_strategy_governed_sources(case, tmp_path)
    service = case["service"]
    paths = service.personal_paths
    output = paths.legacy_output_root
    shutil.copytree(tmp_path / "strategy-versions-copy", output / "backtest/versions")
    for name, value in {"DATA_ROOT": paths.market_root, "OUTPUT_ROOT": output,
        "PERSONAL_STORE_ROOT": paths.personal_root, "PERSONAL_STORE_MODE": "personal",
        "PAPER_CONTRACT_ARTIFACTS_ROOT": tmp_path / "contracts-copy", "PROFILE": "prod"}.items():
        monkeypatch.setenv(name, str(value))
    args = []
    selection = case["selection"]
    for name in selection.__dataclass_fields__:
        args.extend(("--" + name.replace("_", "-"), getattr(selection, name)))
    for name, key in (("thesis-registry", "registry_path"), ("condition-source", "condition_path"),
                     ("metrics-source", "metrics_path"), ("calendar-cache", "calendar_path"),
                     ("calendar-db", "calendar_db_path")):
        args.extend(("--" + name, str(sources[key])))
    args.extend(("--calendar-start-date", "2026-08-03"))
    before = {path: path.read_bytes() for path in (case["stores"].state_db, case["stores"].cost_ledger_db)}
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "passed" and result["writes_account_ledger"] is False
    provider = PortfolioResearchInitialSourceProvider(service, PositionHealthTransitionReadService(output / "position_health_transition"))
    catalogue = provider.list_sources(strategy_id=selection.strategy_id,
        strategy_version_id=selection.strategy_version_id, account_namespace=selection.account_namespace)
    assert len(catalogue.candidates) == 1
    assert catalogue.candidates[0].selection.health_reference.receipt_id == result["receipt_id"]
    assert provider.compare(catalogue.candidates[0].selection, candidate_symbols=("2330",)).request.contexts[0].health_known
    assert {path: path.read_bytes() for path in before} == before


def test_cli_requires_explicit_personal_store_before_writing(tmp_path, monkeypatch):
    for name in ("PERSONAL_STORE_ROOT", "PERSONAL_STORE_MODE", "PAPER_CONTRACT_ARTIFACTS_ROOT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "market"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    with pytest.raises(ValueError, match="PERSONAL"):
        main(["--strategy-id", "s", "--strategy-version-id", "v", "--account-namespace", "a",
              "--operation-id", "op", "--snapshot-id", "snap"])
    assert not (tmp_path / "output/position_health_transition").exists()
