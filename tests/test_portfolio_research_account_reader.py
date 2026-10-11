"""真策略帳戶 writer 到持倉情境 account reader 的隔離回歸。"""
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext

import pytest

from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader,
    StrategyPaperResearchCheckpointSelection,
)
from app_module.strategy_paper_account_availability import StrategyPaperAccountAvailabilityError
from test_strategy_paper_account_daily import (
    _create_account, _seed_account, _writer, _zero_fill_call, _fill_call,
)


def _prepared(tmp_path, monkeypatch, *, filled=False):
    service, paths, manifest = _create_account(tmp_path)
    prior, stores, binding = _seed_account(service, paths, manifest, monkeypatch)
    result_id = "scenario-real-account"
    writer = _writer(service, paths, result_id, {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}})
    result = (_fill_call if filled else _zero_fill_call)(writer, binding, prior, result_id=result_id)
    selection = StrategyPaperResearchCheckpointSelection(
        binding.strategy_id, binding.strategy_version_id, binding.account_namespace,
        result.operation_id, result.snapshot_id,
    )
    return service, stores, binding, result, selection


@pytest.mark.parametrize("filled", [False, True])
def test_real_checkpoint_maps_complete_valuation_and_writer_clock_without_write(tmp_path, monkeypatch, filled):
    service, stores, binding, result, selection = _prepared(tmp_path, monkeypatch, filled=filled)
    before = {path: path.read_bytes() for path in (stores.state_db, stores.cost_ledger_db)}
    reader = StrategyPaperPortfolioResearchAccountReader(service, selection, decision_cutoff=datetime.now(timezone.utc))
    with localcontext(Context(prec=3)):
        account = reader.read_exact(account_kind="paper", portfolio_id=binding.portfolio_id, snapshot_id=result.snapshot_id)
    assert account.valuation.cash_amount == Decimal("399884.98" if filled else "500000.00")
    assert account.capital_amount == Decimal("501884.98" if filled else "500000.00")
    assert {row.stock_code: row.quantity for row in account.positions} == ({"2330": 1000} if filled else {})
    assert [(row.stock_code, row.quantity, row.mark_price, row.market_value) for row in account.valuation.positions] == ([("2330", 1000, Decimal("102"), Decimal("102000.00"))] if filled else [])
    assert account.available_at == result.available_at
    assert account.as_of_date == "2026-08-04"
    assert account.source_hash.startswith("sha256:")
    assert {path: path.read_bytes() for path in before} == before
    assert reader.read_exact(account_kind="paper", portfolio_id=binding.portfolio_id, snapshot_id=result.snapshot_id) == account


@pytest.mark.parametrize("wrong", ["kind", "portfolio", "snapshot"])
def test_reader_rejects_other_kind_account_or_snapshot_without_fallback(tmp_path, monkeypatch, wrong):
    service, stores, binding, result, selection = _prepared(tmp_path, monkeypatch)
    before = stores.state_db.read_bytes()
    reader = StrategyPaperPortfolioResearchAccountReader(service, selection, decision_cutoff=datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        reader.read_exact(account_kind="manual" if wrong == "kind" else "paper", portfolio_id="other-account" if wrong == "portfolio" else binding.portfolio_id, snapshot_id="other-snapshot" if wrong == "snapshot" else result.snapshot_id)
    assert stores.state_db.read_bytes() == before


def test_reader_rejects_checkpoint_unavailable_at_decision_time(tmp_path, monkeypatch):
    service, stores, binding, result, selection = _prepared(tmp_path, monkeypatch)
    before = stores.state_db.read_bytes()
    reader = StrategyPaperPortfolioResearchAccountReader(service, selection, decision_cutoff=datetime(2026, 8, 4, tzinfo=timezone.utc))
    with pytest.raises(StrategyPaperAccountAvailabilityError, match="availability_after_decision_cutoff"):
        reader.read_exact(account_kind="paper", portfolio_id=binding.portfolio_id, snapshot_id=result.snapshot_id)
    assert stores.state_db.read_bytes() == before


def test_selection_and_reader_reject_noncanonical_ids_and_naive_clock():
    with pytest.raises(ValueError, match="selection_strategy_id_invalid"):
        StrategyPaperResearchCheckpointSelection(" strategy", "v1", "namespace", "operation", "snapshot")
    selection = StrategyPaperResearchCheckpointSelection("strategy", "v1", "namespace", "operation", "snapshot")
    with pytest.raises(ValueError, match="timezone_unknown"):
        StrategyPaperPortfolioResearchAccountReader(None, selection, decision_cutoff=datetime(2026, 8, 4))
