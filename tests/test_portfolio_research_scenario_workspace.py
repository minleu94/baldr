"""封存假設重研究仍沿同份現金、時鐘、Health 與原政策。"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app_module.personal_data_paths import PersonalDataPaths
from app_module.portfolio_allocation_dtos import AllocationWeightContract
from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from test_portfolio_research_scenario_repository import _comparison, _route


@pytest.fixture
def workspace(tmp_path):
    paths = PersonalDataPaths(market_root=tmp_path / "market", legacy_output_root=tmp_path / "legacy",
                             personal_root=tmp_path / "market" / "personal")
    repo = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    comparison = _comparison()
    saved = repo.append(comparison, saved_at=datetime(2026, 10, 9, 2, tzinfo=timezone.utc))
    return PortfolioResearchScenarioWorkspace(repo), saved


def test_new_target_preserves_original_complete_facts_and_save_reopens(workspace):
    service, saved = workspace
    original = encode_scenario_artifact(saved.comparison)
    target = AllocationWeightContract({"2330": 1200, "2382": 800}, 8000)
    preview = service.compare_target(saved.artifact_id, account_kind="paper", portfolio_id="account-a", explicit_weights=target)
    assert preview.account == saved.comparison.account
    assert preview.request == replace(saved.comparison.request, explicit_weights=target)
    assert preview.scenarios[-1].result.requested_weights == target
    assert preview.input_hash != saved.comparison.input_hash
    assert service.repository.list_artifact_ids(account_kind="paper", portfolio_id="account-a") == (saved.artifact_id,)
    new = service.save_target(saved.artifact_id, preview, account_kind="paper", portfolio_id="account-a")
    assert new.artifact_id != saved.artifact_id
    assert service.open_exact(new.artifact_id, account_kind="paper", portfolio_id="account-a").comparison == preview
    assert encode_scenario_artifact(service.open_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a").comparison) == original
    assert len(service.list_saved(account_kind="paper", portfolio_id="account-a")) == 2


def test_other_account_and_unselected_symbol_fail_closed(workspace):
    service, saved = workspace
    with pytest.raises(ValueError, match="another selected account"):
        service.open_exact(saved.artifact_id, account_kind="manual", portfolio_id="account-a")
    with pytest.raises(ValueError, match="unselected symbol"):
        service.compare_target(saved.artifact_id, account_kind="paper", portfolio_id="account-a",
                               explicit_weights=AllocationWeightContract({"9999": 1000}, 9000))


def test_cancel_does_not_save_and_forged_preview_cannot_replace_source(workspace):
    service, saved = workspace
    args = dict(account_kind="paper", portfolio_id="account-a")
    target = AllocationWeightContract({"2330": 1000}, 9000)
    with pytest.raises(InterruptedError):
        service.compare_target(saved.artifact_id, explicit_weights=target, cancel_callback=lambda: True, **args)
    foreign = _comparison(account_id="account-b")
    with pytest.raises(ValueError, match="不是從所選封存"):
        service.save_target(saved.artifact_id, foreign, **args)
    assert service.list_saved(**args) == (saved.artifact_id,)


def test_policy_change_keeps_old_readable_but_blocks_recalculation(workspace, monkeypatch):
    service, saved = workspace
    original_factory = __import__("app_module.portfolio_research_scenario_workspace", fromlist=["PortfolioAllocationService"])
    class DifferentPolicy:
        allocation_policy_hash = "sha256:" + "f" * 64
    monkeypatch.setattr(original_factory, "PortfolioAllocationService", DifferentPolicy)
    assert service.open_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a") == saved
    with pytest.raises(ValueError, match="政策版本"):
        service.compare_target(saved.artifact_id, account_kind="paper", portfolio_id="account-a",
                               explicit_weights=AllocationWeightContract({"2330": 1000}, 9000))
