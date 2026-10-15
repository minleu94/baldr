"""由精確策略 checkpoint 投影同份帳戶與 Position Health 原列身分。"""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Context, localcontext
import hashlib
import json

import pytest

from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader,
    StrategyPaperResearchCheckpointSelection,
    StrategyPaperResearchHealthSource,
)
from app_module.position_health_daily_refresh_service import (
    PaperHealthSnapshotPosition,
    paper_health_snapshot_rows_sha256,
)
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailabilityError,
    read_exact_strategy_paper_account_checkpoint,
)
from test_strategy_paper_account_daily import (
    _create_account,
    _seed_account,
    _writer,
    _zero_fill_call,
    _fill_call,
)


def _prepared(tmp_path, monkeypatch, *, filled=False):
    service, paths, manifest = _create_account(tmp_path)
    prior, stores, binding = _seed_account(service, paths, manifest, monkeypatch)
    result_id = "scenario-real-account"
    writer = _writer(
        service,
        paths,
        result_id,
        {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}},
    )
    result = (_fill_call if filled else _zero_fill_call)(
        writer, binding, prior, result_id=result_id
    )
    selection = StrategyPaperResearchCheckpointSelection(
        binding.strategy_id,
        binding.strategy_version_id,
        binding.account_namespace,
        result.operation_id,
        result.snapshot_id,
    )
    return service, stores, binding, result, selection


def _expected_rows_hash(
    *,
    snapshot_id: str,
    portfolio_id: str,
    decision_date: str,
    source_result_id: str,
    positions: tuple[PaperHealthSnapshotPosition, ...],
) -> str:
    payload = {
        "snapshot_id": snapshot_id,
        "portfolio_id": portfolio_id,
        "decision_date": decision_date,
        "source_result_id": source_result_id,
        "positions": [
            {
                "stock_code": row.stock_code,
                "executable_shares": row.shares,
                "constrained_weight_bp": row.weight_bp,
            }
            for row in positions
        ],
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("filled", [False, True])
def test_health_source_reuses_one_exact_checkpoint_and_preserves_account(
    tmp_path, monkeypatch, filled
):
    service, stores, binding, result, selection = _prepared(
        tmp_path, monkeypatch, filled=filled
    )
    database_paths = (stores.state_db, stores.cost_ledger_db)
    before = {path: path.read_bytes() for path in database_paths}
    reader = StrategyPaperPortfolioResearchAccountReader(
        service, selection, decision_cutoff=datetime.now(timezone.utc)
    )

    with localcontext(Context(prec=3)):
        account_before = reader.read_exact(
            account_kind="paper",
            portfolio_id=binding.portfolio_id,
            snapshot_id=result.snapshot_id,
        )
        source = reader.read_health_source(
            portfolio_id=binding.portfolio_id,
            snapshot_id=result.snapshot_id,
        )
        account_after = reader.read_exact(
            account_kind="paper",
            portfolio_id=binding.portfolio_id,
            snapshot_id=result.snapshot_id,
        )

    checkpoint = read_exact_strategy_paper_account_checkpoint(
        service,
        strategy_id=selection.strategy_id,
        strategy_version_id=selection.strategy_version_id,
        account_namespace=selection.account_namespace,
        operation_id=selection.operation_id,
        snapshot_id=selection.snapshot_id,
        decision_cutoff=datetime.now(timezone.utc),
    )
    expected_positions = tuple(
        PaperHealthSnapshotPosition(row.stock_code, row.quantity, row.weight_bp)
        for row in sorted(checkpoint.snapshot.positions, key=lambda item: item.stock_code)
    )
    assert isinstance(source, StrategyPaperResearchHealthSource)
    assert source.selection == selection
    assert source.account == account_before == account_after
    assert source.positions == expected_positions
    assert source.snapshot_source_result_id == checkpoint.snapshot.source_result_id
    assert source.checkpoint_snapshot_sha256 == checkpoint.availability.snapshot_sha256
    assert source.checkpoint_snapshot_sha256 != source.source_snapshot_rows_sha256

    expected_rows_hash = _expected_rows_hash(
        snapshot_id=source.account.snapshot_id,
        portfolio_id=source.account.portfolio_id,
        decision_date=source.account.as_of_date,
        source_result_id=source.snapshot_source_result_id,
        positions=source.positions,
    )
    assert source.source_snapshot_rows_sha256 == expected_rows_hash
    assert paper_health_snapshot_rows_sha256(
        snapshot_id=source.account.snapshot_id,
        portfolio_id=source.account.portfolio_id,
        decision_date=source.account.as_of_date,
        source_result_id=source.snapshot_source_result_id,
        positions=source.positions,
    ) == expected_rows_hash
    assert source.source_hash == reader.read_health_source(
        portfolio_id=binding.portfolio_id,
        snapshot_id=result.snapshot_id,
    ).source_hash
    assert source.source_hash != source.account.source_hash
    assert {path: path.read_bytes() for path in database_paths} == before


def test_health_rows_hash_covers_zero_share_raw_rows():
    positions = (
        PaperHealthSnapshotPosition("2317", 0, 0),
        PaperHealthSnapshotPosition("2330", 1000, 2500),
    )
    identity = {
        "snapshot_id": "snapshot-1",
        "portfolio_id": "acct-1",
        "decision_date": "2026-08-04",
        "source_result_id": "source-1",
    }
    actual = paper_health_snapshot_rows_sha256(**identity, positions=positions)
    assert actual == _expected_rows_hash(**identity, positions=positions)
    assert actual != paper_health_snapshot_rows_sha256(**identity, positions=positions[1:])


def test_health_source_hash_changes_with_distinct_real_checkpoint_inputs(
    tmp_path, monkeypatch
):
    zero_dir = tmp_path / "zero-fill"
    filled_dir = tmp_path / "filled"
    zero_dir.mkdir()
    filled_dir.mkdir()
    zero_service, _, zero_binding, zero_result, zero_selection = _prepared(
        zero_dir, monkeypatch, filled=False
    )
    filled_service, _, filled_binding, filled_result, filled_selection = _prepared(
        filled_dir, monkeypatch, filled=True
    )
    zero_reader = StrategyPaperPortfolioResearchAccountReader(
        zero_service, zero_selection, decision_cutoff=datetime.now(timezone.utc)
    )
    filled_reader = StrategyPaperPortfolioResearchAccountReader(
        filled_service, filled_selection, decision_cutoff=datetime.now(timezone.utc)
    )

    zero_source = zero_reader.read_health_source(
        portfolio_id=zero_binding.portfolio_id,
        snapshot_id=zero_result.snapshot_id,
    )
    filled_source = filled_reader.read_health_source(
        portfolio_id=filled_binding.portfolio_id,
        snapshot_id=filled_result.snapshot_id,
    )

    assert zero_source.source_hash != filled_source.source_hash
    assert zero_source.account.source_hash != filled_source.account.source_hash


def test_health_source_rejects_wrong_identity_and_unavailable_cutoff_without_write(
    tmp_path, monkeypatch
):
    service, stores, binding, result, selection = _prepared(tmp_path, monkeypatch)
    before = {path: path.read_bytes() for path in (stores.state_db, stores.cost_ledger_db)}
    reader = StrategyPaperPortfolioResearchAccountReader(
        service, selection, decision_cutoff=datetime.now(timezone.utc)
    )

    with pytest.raises(ValueError):
        reader.read_health_source(
            portfolio_id="other-account", snapshot_id=result.snapshot_id
        )
    with pytest.raises(ValueError):
        reader.read_health_source(
            portfolio_id=binding.portfolio_id, snapshot_id="other-snapshot"
        )

    early_reader = StrategyPaperPortfolioResearchAccountReader(
        service,
        selection,
        decision_cutoff=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_after_decision_cutoff",
    ):
        early_reader.read_health_source(
            portfolio_id=binding.portfolio_id, snapshot_id=result.snapshot_id
        )
    assert {path: path.read_bytes() for path in before} == before


def test_health_source_rejects_tampered_checkpoint_proof(tmp_path, monkeypatch):
    service, _, binding, result, selection = _prepared(tmp_path, monkeypatch)
    reader = StrategyPaperPortfolioResearchAccountReader(
        service, selection, decision_cutoff=datetime.now(timezone.utc)
    )
    source = reader.read_health_source(
        portfolio_id=binding.portfolio_id, snapshot_id=result.snapshot_id
    )

    with pytest.raises(ValueError, match="research_health_account_source_hash_mismatch"):
        replace(source, operation_sha256="sha256:" + "0" * 64)
