from decimal import Decimal
from pathlib import Path

import pytest

from app_module.paper_trade_ledger import PaperTradeFill, PaperTradeLedgerRepository, PaperTradeTransition
from tests.test_research_paper_evidence_binding import _build_paper_fixture


def _filled_event(portfolio_id: str):
    fill = PaperTradeFill(
        fill_id="rollback-fill",
        order_id="rollback-order",
        portfolio_id=portfolio_id,
        event_date="2026-10-21",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=1000,
        reference_price=Decimal("50.00"),
        fill_price=Decimal("50.05"),
        commission=Decimal("75.08"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("50.00"),
        turnover_bp=1000,
        execution_gap_bp=10,
        status="filled",
        source_event_id="rollback-source-event",
    )
    transition = PaperTradeTransition(
        transition_id="rollback-transition",
        batch_id="rollback-batch",
        portfolio_id=portfolio_id,
        event_date="2026-10-21",
        fill_ids=(fill.fill_id,),
        pre_cash=Decimal("500000.00"),
        pre_total_value=Decimal("500000.00"),
        post_cash=Decimal("449874.92"),
        post_total_value=Decimal("499874.92"),
        common_nav=Decimal("500000.00"),
        common_prices={"2330": Decimal("50.00")},
        pre_positions={},
        post_positions={"2330": 1000},
    )
    return fill, transition


def test_read_rowset_snapshot_returns_one_bound_read_only_state(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    reader = PaperTradeLedgerRepository(
        fixture.paths.cost_ledger_db,
        route=fixture.route,
        personal_paths=fixture.personal_paths,
        portfolio_id=fixture.binding.portfolio_id,
        read_only=True,
    )
    before = reader.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id)
    assert before.fills == ()
    assert before.transitions == ()
    assert before.rowset_hash == reader.rowset_hash()
    assert reader._read_only is True
    fill, transition = _filled_event(fixture.binding.portfolio_id)
    fixture.ledger.append_daily_operation(
        operation_id="snapshot-coherent-operation",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-21",
        expected_rowset_hash=before.rowset_hash,
        fills=(fill,),
        transition=transition,
    )
    after = reader.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id)
    assert after.fills == (fill,)
    assert after.transitions == (transition,)
    assert after.rowset_hash == fixture.ledger.rowset_hash()


def test_failed_transition_insert_rolls_back_fill_and_operation_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = _build_paper_fixture(tmp_path)
    fill, transition = _filled_event(fixture.binding.portfolio_id)
    before = fixture.ledger.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id)

    def fail_transition_insert(_connection, _transition):
        raise RuntimeError("fixture failure after fill insert")

    monkeypatch.setattr(fixture.ledger, "_insert_daily_transition", fail_transition_insert)
    with pytest.raises(RuntimeError, match="after fill insert"):
        fixture.ledger.append_daily_operation(
            operation_id="rollback-operation",
            portfolio_id=fixture.binding.portfolio_id,
            event_date="2026-10-21",
            expected_rowset_hash=before.rowset_hash,
            fills=(fill,),
            transition=transition,
        )

    after = fixture.ledger.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id)
    assert after.fills == ()
    assert after.transitions == ()
    assert after.rowset_hash == before.rowset_hash
    assert fixture.ledger.get_daily_operation(
        "rollback-operation", portfolio_id=fixture.binding.portfolio_id
    ) is None
