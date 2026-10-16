"""首次配置研究沿真 writer 來源、原 evaluator 與原 store 的旅程。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.portfolio_allocation_dtos import AllocationWeightContract
from app_module.portfolio_research_account_reader import StrategyPaperPortfolioResearchAccountReader, _weekly_turnover
from app_module.portfolio_research_initial_source import (
    InitialPortfolioResearchSelection, PortfolioResearchInitialSourceProvider,
)
from app_module.position_health_strategy_archive import (
    StrategyHealthArchiveCandidate, read_strategy_saved_health_exact,
)
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from app_module.portfolio_research_scenario_service import PortfolioResearchScenarioService
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.strategy_paper_account_availability import read_exact_strategy_paper_account_checkpoint
from test_portfolio_research_scenario_repository import _route
from test_position_health_strategy_archive import (
    _prepared_pipeline, _write_strategy_governed_sources, _publish,
)


def _initial_case(tmp_path, monkeypatch, *, governed=True):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    if governed:
        sources = _write_strategy_governed_sources(case, tmp_path)
        case["evaluated"] = evaluate_baseline_file(
            baseline_path=case["baseline_path"], output_dir=case["archive_root"],
            observed_at=sources["observed_at"], decision_date=case["baseline"]["decision_date"],
            thesis_registry_path=sources["registry_path"], condition_source_path=sources["condition_path"],
            metrics_source_path=sources["metrics_path"], calendar_cache_path=sources["calendar_path"],
            calendar_db_path=sources["calendar_db_path"], calendar_start_date="2026-08-03",
        )
        assert case["evaluated"]["status"] == "passed", case["evaluated"]
    reference = _publish(case)
    selection = InitialPortfolioResearchSelection(case["selection"], reference)
    paths = case["service"].personal_paths
    repository = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    provider = PortfolioResearchInitialSourceProvider(case["service"], case["transition_reader"])
    return case, selection, PortfolioResearchScenarioWorkspace(repository, initial_source_provider=provider)


def test_initial_compare_save_and_exact_reopen_preserve_original_account(tmp_path, monkeypatch):
    case, selection, workspace = _initial_case(tmp_path, monkeypatch)
    originals = {path: path.read_bytes() for path in (case["stores"].state_db, case["stores"].cost_ledger_db)}
    candidates = workspace.list_initial_sources(strategy_id=selection.checkpoint.strategy_id,
        strategy_version_id=selection.checkpoint.strategy_version_id, account_namespace=selection.checkpoint.account_namespace)
    assert [row.selection for row in candidates.candidates] == [selection]
    assert not candidates.truncated
    import app_module.portfolio_research_initial_source as initial_module
    exact_read = initial_module.read_strategy_saved_health_exact
    exact_cutoffs = []

    def record_exact_cutoff(**kwargs):
        exact_cutoffs.append(kwargs["decision_cutoff"])
        return exact_read(**kwargs)

    monkeypatch.setattr(initial_module, "read_strategy_saved_health_exact", record_exact_cutoff)
    with localcontext(Context(prec=3)):
        comparison = workspace.compare_initial(selection, candidate_symbols=("2330",))
        saved = workspace.save_initial(selection, comparison)
    assert exact_cutoffs == [comparison.decision_at, comparison.decision_at]
    exact_health = read_strategy_saved_health_exact(
        reader=case["transition_reader"], reference=selection.health_reference,
        account_reader=StrategyPaperPortfolioResearchAccountReader(
            case["service"], selection.checkpoint, decision_cutoff=datetime.now(timezone.utc),
        ), portfolio_id=selection.checkpoint.account_namespace,
        snapshot_id=selection.checkpoint.snapshot_id, decision_cutoff=datetime.now(timezone.utc),
    )
    assert comparison.account.positions[0].quantity == 1000
    assert comparison.decision_at == exact_health.available_at
    assert comparison.account.valuation.positions[0].mark_price == Decimal("102.00")
    assert comparison.request.contexts[0].context.market_data_as_of_date == "2026-08-03"
    assert comparison.request.contexts[0].context.health_state == "EXIT_CANDIDATE"
    assert comparison.request.contexts[0].context.median_volume_20d_shares is None
    assert comparison.request.contexts[0].context.trading_days_since_last_trade is None
    assert workspace.open_exact(saved.artifact_id, account_kind="paper",
        portfolio_id=selection.checkpoint.account_namespace).comparison == comparison
    assert {path: path.read_bytes() for path in originals} == originals


def test_initial_list_excludes_health_saved_after_its_decision_day(tmp_path, monkeypatch):
    _case, selection, workspace = _initial_case(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    taipei_today = now.astimezone(ZoneInfo("Asia/Taipei")).date()
    import app_module.portfolio_research_initial_source as initial_module

    monkeypatch.setattr(initial_module, "list_strategy_paper_account_checkpoint_candidates",
                        lambda *_args, **_kwargs: SimpleNamespace(rows=(SimpleNamespace(
                            row_state="candidate_pending_exact_reader", operation_id=selection.checkpoint.operation_id,
                            snapshot_id=selection.checkpoint.snapshot_id,
                        ),), truncated=False))
    monkeypatch.setattr(initial_module, "list_strategy_saved_health_receipts",
                        lambda **_kwargs: ((
                            StrategyHealthArchiveCandidate(selection.checkpoint, selection.health_reference,
                                                           taipei_today.isoformat(), now.isoformat()),
                            StrategyHealthArchiveCandidate(selection.checkpoint, selection.health_reference,
                                                           (taipei_today - timedelta(days=1)).isoformat(), now.isoformat()),
                        ), False))
    catalogue = workspace.list_initial_sources(
        strategy_id=selection.checkpoint.strategy_id,
        strategy_version_id=selection.checkpoint.strategy_version_id,
        account_namespace=selection.checkpoint.account_namespace,
    )
    assert len(catalogue.candidates) == 1
    assert catalogue.later_day_receipts == 1
    assert "可得" in catalogue.candidates[0].label


def test_initial_compare_rejects_receipt_outside_health_decision_day(tmp_path, monkeypatch):
    _case, selection, workspace = _initial_case(tmp_path, monkeypatch)
    import app_module.portfolio_research_initial_source as initial_module
    list_receipts = initial_module.list_strategy_saved_health_receipts

    def late_health(**kwargs):
        rows, truncated = list_receipts(**kwargs)
        return tuple(replace(row, decision_date=(
            datetime.fromisoformat(row.decision_date).date() - timedelta(days=1)
        ).isoformat()) for row in rows), truncated

    monkeypatch.setattr(initial_module, "list_strategy_saved_health_receipts", late_health)
    with pytest.raises(ValueError, match="不能倒填原日研究決策時間"):
        workspace.compare_initial(selection, candidate_symbols=("2330",))
    assert workspace.list_saved(account_kind="paper", portfolio_id=selection.checkpoint.account_namespace) == ()


def test_initial_missing_health_stays_unavailable_and_unheld_candidate_not_fabricated(tmp_path, monkeypatch):
    case, selection, workspace = _initial_case(tmp_path, monkeypatch, governed=False)
    with pytest.raises(ValueError, match="Health 來源缺件"):
        workspace.compare_initial(selection, candidate_symbols=("2330",))
    assert workspace.list_saved(account_kind="paper", portfolio_id=selection.checkpoint.account_namespace) == ()
    with pytest.raises(ValueError, match="不能補造未持有候選"):
        workspace.compare_initial(selection, candidate_symbols=("1111",))


def test_initial_cancel_and_forged_preview_do_not_append(tmp_path, monkeypatch):
    case, selection, workspace = _initial_case(tmp_path, monkeypatch)
    comparison = workspace.compare_initial(selection, candidate_symbols=("2330",))
    with pytest.raises(InterruptedError):
        workspace.save_initial(selection, comparison, cancel_callback=lambda: True)
    class OriginalAccount:
        def read_exact(self, **_kwargs):
            return comparison.account
    forged = PortfolioResearchScenarioService(OriginalAccount()).compare(replace(
        comparison.request, research_source_hash="sha256:" + "0" * 64))
    with pytest.raises(ValueError):
        workspace.save_initial(selection, forged)
    with pytest.raises(ValueError, match="external_receipt_hash_mismatch"):
        workspace.compare_initial(replace(selection, health_reference=replace(
            selection.health_reference, receipt_sha256="sha256:" + "f" * 64)), candidate_symbols=("2330",))
    assert workspace.list_saved(account_kind="paper", portfolio_id=selection.checkpoint.account_namespace) == ()


def test_source_turnover_uses_canonical_common_price_weights_and_rolling_window(tmp_path, monkeypatch):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    selected = case["selection"]
    checkpoint = read_exact_strategy_paper_account_checkpoint(case["service"],
        **{key: getattr(selected, key) for key in selected.__dataclass_fields__},
        decision_cutoff=datetime.now(timezone.utc), allocation_decision_date="2026-08-05")
    assert checkpoint.ordered_fills[0].turnover_bp == 2002
    with localcontext(Context(prec=3)):
        assert _weekly_turnover(checkpoint, "2026-08-05") == 2000
        assert _weekly_turnover(checkpoint, "2026-08-11") == 0
