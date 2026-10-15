"""驗證 daily checkpoint 的 allocation 決策日前綴讀回契約。"""

from dataclasses import replace
from datetime import date, timedelta
import sqlite3

import pytest

from app_module.paper_trade_ledger import PaperTradeLedgerRepository
from test_portfolio_research_health_source import _prepared


def _day_offset(event_date: str, days: int) -> str:
    return (date.fromisoformat(event_date) + timedelta(days=days)).isoformat()


def test_allocation_prefix_preserves_original_order_and_checkpoint_hash(
    tmp_path, monkeypatch
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=True
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None
    decision_date = _day_offset(marker.event_date, 1)
    before = stores.cost_ledger_db.read_bytes()

    original = ledger.read_exact_daily_operation(
        marker.operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=marker.event_date,
    )
    observed = ledger.read_exact_daily_operation(
        marker.operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=marker.event_date,
        allocation_decision_date=decision_date,
    )

    assert original.transition is not None
    assert observed.ordered_fills == original.ordered_fills
    assert observed.transition == original.transition
    assert tuple(fill.fill_id for fill in observed.ordered_fills) == marker.ordered_fill_ids
    assert observed.allocation_decision_date == decision_date
    assert observed.allocation_prefix_fills == original.ordered_fills
    assert observed.allocation_prefix_transitions == (original.transition,)
    assert observed.allocation_prefix_rowset_hash == marker.rowset_hash_after
    assert observed.rowset_hash_after == marker.rowset_hash_after
    assert stores.cost_ledger_db.read_bytes() == before


@pytest.mark.parametrize("days_after_execution", [0, -1])
def test_allocation_decision_must_follow_execution_without_writing(
    tmp_path, monkeypatch, days_after_execution
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=False
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None
    before = stores.cost_ledger_db.read_bytes()

    with pytest.raises(
        ValueError, match="paper allocation decision must follow checkpoint execution"
    ):
        ledger.read_exact_daily_operation(
            marker.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=marker.event_date,
            allocation_decision_date=_day_offset(
                marker.event_date, days_after_execution
            ),
        )

    assert stores.cost_ledger_db.read_bytes() == before


def test_old_checkpoint_rejects_later_zero_fill_operation_before_decision(
    tmp_path, monkeypatch
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=False
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None and marker.zero_fill
    later_date = _day_offset(marker.event_date, 1)
    decision_date = _day_offset(marker.event_date, 2)
    later_operation_id = "allocation-prefix-later-zero-fill"
    ledger.append_daily_operation(
        operation_id=later_operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=later_date,
        expected_rowset_hash=ledger.rowset_hash(),
        fills=(),
        transition=None,
    )
    later_marker = ledger.get_daily_operation(
        later_operation_id, portfolio_id=binding.portfolio_id
    )
    assert later_marker is not None and later_marker.zero_fill
    before = stores.cost_ledger_db.read_bytes()

    with pytest.raises(
        ValueError, match="paper allocation checkpoint has later ledger operations"
    ):
        ledger.read_exact_daily_operation(
            marker.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=marker.event_date,
            allocation_decision_date=decision_date,
        )

    assert stores.cost_ledger_db.read_bytes() == before


def test_allocation_prefix_rejects_missing_operation_link_without_writing(
    tmp_path, monkeypatch
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=True
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None
    original = ledger.read_exact_daily_operation(
        marker.operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=marker.event_date,
    )
    assert original.ordered_fills and original.transition is not None

    middle_date = _day_offset(marker.event_date, 1)
    final_date = _day_offset(marker.event_date, 2)
    decision_date = _day_offset(marker.event_date, 3)
    source_fill = original.ordered_fills[0]
    middle_fill = replace(
        source_fill,
        fill_id="allocation-prefix-middle-fill",
        order_id="allocation-prefix-middle-order",
        event_date=middle_date,
        source_event_id="allocation-prefix-middle-event",
    )
    middle_transition = replace(
        original.transition,
        transition_id="allocation-prefix-middle-transition",
        batch_id="allocation-prefix-middle-batch",
        event_date=middle_date,
        fill_ids=(middle_fill.fill_id,),
    )
    middle_operation_id = "allocation-prefix-middle-operation"
    ledger.append_daily_operation(
        operation_id=middle_operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=middle_date,
        expected_rowset_hash=ledger.rowset_hash(),
        fills=(middle_fill,),
        transition=middle_transition,
    )
    final_operation_id = "allocation-prefix-final-zero-fill"
    ledger.append_daily_operation(
        operation_id=final_operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=final_date,
        expected_rowset_hash=ledger.rowset_hash(),
        fills=(),
        transition=None,
    )
    with sqlite3.connect(stores.cost_ledger_db) as connection:
        connection.execute(
            "DELETE FROM paper_trade_daily_operations WHERE operation_id = ?",
            (middle_operation_id,),
        )
    before = stores.cost_ledger_db.read_bytes()

    with pytest.raises(ValueError, match="paper daily operation append chain mismatch"):
        ledger.read_exact_daily_operation(
            final_operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=final_date,
            allocation_decision_date=decision_date,
        )

    assert stores.cost_ledger_db.read_bytes() == before


def test_allocation_prefix_rejects_foreign_fill_without_writing(
    tmp_path, monkeypatch
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=True
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None and marker.ordered_fill_ids
    with sqlite3.connect(stores.cost_ledger_db) as connection:
        connection.execute(
            "UPDATE paper_trade_ledger SET portfolio_id = ? WHERE fill_id = ?",
            ("foreign-allocation-portfolio", marker.ordered_fill_ids[0]),
        )
    before = stores.cost_ledger_db.read_bytes()

    with pytest.raises(
        ValueError, match="paper exact-read foreign portfolio prefix row"
    ):
        ledger.read_exact_daily_operation(
            marker.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=marker.event_date,
            allocation_decision_date=_day_offset(marker.event_date, 1),
        )

    assert stores.cost_ledger_db.read_bytes() == before


def test_allocation_prefix_rejects_missing_transition_without_writing(
    tmp_path, monkeypatch
):
    _, stores, binding, result, _ = _prepared(
        tmp_path, monkeypatch, filled=True
    )
    ledger = PaperTradeLedgerRepository(stores.cost_ledger_db)
    marker = ledger.get_daily_operation(
        result.operation_id, portfolio_id=binding.portfolio_id
    )
    assert marker is not None and marker.transition_id is not None
    with sqlite3.connect(stores.cost_ledger_db) as connection:
        connection.execute(
            "DELETE FROM paper_trade_transitions WHERE transition_id = ?",
            (marker.transition_id,),
        )
    before = stores.cost_ledger_db.read_bytes()

    with pytest.raises(ValueError, match="paper daily operation transition is missing"):
        ledger.read_exact_daily_operation(
            marker.operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=marker.event_date,
            allocation_decision_date=_day_offset(marker.event_date, 1),
        )

    assert stores.cost_ledger_db.read_bytes() == before
