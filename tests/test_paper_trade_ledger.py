from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
import sqlite3
from threading import Event, Thread

import pytest

import app_module.paper_trade_ledger as paper_trade_ledger_module
from app_module.paper_trade_ledger import (
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)


def _fill(
    fill_id: str = "fill-1",
    *,
    status: str = "filled",
    requested: int = 1000,
    filled: int = 1000,
    turnover_bp: int | None = 120,
    execution_gap_bp: int | None = 8,
) -> PaperTradeFill:
    return PaperTradeFill(
        fill_id=fill_id,
        order_id="order-1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        stock_code="2330",
        side="buy",
        requested_quantity=requested,
        filled_quantity=filled,
        reference_price=Decimal("100.00"),
        fill_price=Decimal("100.08") if filled else None,
        commission=Decimal("15.00"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("8.00"),
        turnover_bp=turnover_bp,
        execution_gap_bp=execution_gap_bp,
        status=status,
        source_event_id=f"event-{fill_id}",
    )


def _transition(
    fill_ids: tuple[str, ...],
    *,
    transition_id: str = "transition-daily-1",
) -> PaperTradeTransition:
    return PaperTradeTransition(
        transition_id=transition_id,
        batch_id="batch-daily-1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        fill_ids=fill_ids,
        pre_cash=Decimal("500000.00"),
        pre_total_value=Decimal("500000.00"),
        post_cash=Decimal("399905.00"),
        post_total_value=Decimal("499905.00"),
        common_nav=Decimal("500000.00"),
        common_prices={"2330": Decimal("100.00")},
        pre_positions={},
        post_positions={"2330": 1000},
    )


def test_paper_fill_is_decimal_and_roundtrips_append_only(tmp_path: Path) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "paper_trade.sqlite")
    fill = _fill()

    repository.append(fill)
    loaded = repository.list()

    assert loaded == (fill,)
    assert loaded[0].total_cost == Decimal("23.00")
    assert loaded[0].cash_settlement_cost == Decimal("15.00")
    assert loaded[0].gross_amount == Decimal("100080.00")
    assert loaded[0].cost_record_ready is True
    assert loaded[0].to_dict()["research_only"] is True
    # 新的現金語意是 property，不改既有 payload/hash 欄位。
    assert "cash_settlement_cost" not in loaded[0].to_dict()


def test_partial_fill_requires_partial_quantity_and_gap() -> None:
    partial = _fill(
        status="partially_filled",
        requested=1000,
        filled=400,
        execution_gap_bp=12,
    )
    assert partial.filled_quantity == 400

    with pytest.raises(ValueError, match="partially_filled status"):
        _fill(status="partially_filled", requested=1000, filled=1000)
    with pytest.raises(ValueError, match="execution_gap_bp"):
        _fill(status="filled", execution_gap_bp=None)
    assert _fill(execution_gap_bp=-12).execution_gap_bp == -12
    with pytest.raises(ValueError, match="execution_gap_bp"):
        _fill(execution_gap_bp=True)  # type: ignore[arg-type]


def test_rejected_event_has_no_fill_price_or_filled_quantity() -> None:
    rejected = PaperTradeFill(
        fill_id="fill-rejected",
        order_id="order-rejected",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=0,
        reference_price=Decimal("100.00"),
        fill_price=None,
        commission=Decimal("0"),
        tax=Decimal("0"),
        slippage_cost=Decimal("0"),
        turnover_bp=0,
        execution_gap_bp=None,
        status="rejected",
        source_event_id="event-rejected",
    )
    assert rejected.gross_amount == Decimal("0.00")


def test_append_many_is_atomic_when_duplicate_fill_id_is_present(tmp_path: Path) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "paper_trade.sqlite")

    with pytest.raises(ValueError, match="already exists"):
        repository.append_many((_fill("fill-1"), _fill("fill-1")))

    assert repository.list() == ()


def test_source_event_identity_is_scoped_to_portfolio_but_unique_within_it(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "paper_trade.sqlite")
    shared_event = "source-system-event-1"
    first = replace(
        _fill("portfolio-a-fill"),
        portfolio_id="portfolio-a",
        source_event_id=shared_event,
    )
    second = replace(
        _fill("portfolio-b-fill"),
        portfolio_id="portfolio-b",
        source_event_id=shared_event,
    )
    repository.append_many((first, second))
    assert repository.list(portfolio_id="portfolio-a") == (first,)
    assert repository.list(portfolio_id="portfolio-b") == (second,)

    conflicting = replace(
        _fill("portfolio-a-conflict"),
        portfolio_id="portfolio-a",
        source_event_id=shared_event,
    )
    with pytest.raises(ValueError, match="portfolio/source_event_id"):
        repository.append(conflicting)
    assert repository.list(portfolio_id="portfolio-a") == (first,)


def test_begin_immediate_serializes_concurrent_writers_and_preserves_one_batch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "paper_trade.sqlite"
    fill = _fill("concurrent-fill")

    def append_once() -> str:
        try:
            PaperTradeLedgerRepository(db_path).append(fill)
        except ValueError as error:
            return str(error)
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(lambda _: append_once(), range(2)))

    assert sorted(outcomes) == [
        "committed",
        "paper trade fill already exists: fill_id or portfolio/source_event_id",
    ]
    loaded = PaperTradeLedgerRepository(db_path).list()
    assert loaded == (fill,)
    # The persisted values are the exact Decimal ledger values used by the
    # producer's cash projection; no partial second commit is present.
    assert loaded[0].gross_amount + loaded[0].cash_settlement_cost == Decimal(
        "100095.00"
    )


def test_daily_operation_cas_persists_ordered_batch_and_exact_retry(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "daily-ledger.sqlite")
    fills = (_fill("fill-z"), _fill("fill-a"))
    transition = _transition(tuple(item.fill_id for item in fills))
    before = repository.rowset_hash()

    result = repository.append_daily_operation(
        operation_id="daily-20260827-v1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        expected_rowset_hash=before,
        fills=fills,
        transition=transition,
    )

    assert result.status == "appended"
    assert result.rowset_hash_before == before
    assert result.rowset_hash_after == repository.rowset_hash()
    assert result.ordered_fill_ids == ("fill-z", "fill-a")
    marker = repository.get_daily_operation("daily-20260827-v1")
    assert marker is not None
    assert marker.ordered_fill_ids == result.ordered_fill_ids
    assert marker.zero_fill is False
    assert repository.list_transitions() == (transition,)

    retry = repository.append_daily_operation(
        operation_id="daily-20260827-v1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        expected_rowset_hash=before,
        fills=fills,
        transition=transition,
    )
    assert retry.status == "already_committed"

    assert retry.rowset_hash_after == result.rowset_hash_after
    assert repository.rowset_hash() == result.rowset_hash_after

    with pytest.raises(ValueError, match="identity conflicts"):
        repository.append_daily_operation(
            operation_id="daily-20260827-v1",
            portfolio_id="paper-main",
            event_date="2026-08-27",
            expected_rowset_hash=before,
            fills=tuple(reversed(fills)),
            transition=replace(transition, fill_ids=("fill-a", "fill-z")),
        )


def test_daily_operation_zero_fill_is_an_explicit_idempotent_checkpoint(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "zero-fill.sqlite")
    before = repository.rowset_hash()

    result = repository.append_daily_operation(
        operation_id="zero-fill-20260827-v1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        expected_rowset_hash=before,
        fills=(),
        transition=None,
    )

    assert result.status == "appended"
    assert result.rowset_hash_before == result.rowset_hash_after == before
    marker = repository.get_daily_operation("zero-fill-20260827-v1")
    assert marker is not None
    assert marker.zero_fill is True
    assert marker.ordered_fill_ids == ()
    assert repository.list() == ()
    assert repository.list_transitions() == ()

    retry = repository.append_daily_operation(
        operation_id="zero-fill-20260827-v1",
        portfolio_id="paper-main",
        event_date="2026-08-27",
        expected_rowset_hash=before,
        fills=(),
        transition=None,
    )
    assert retry.status == "already_committed"

    with pytest.raises(ValueError, match="portfolio/event_date"):
        repository.append_daily_operation(
            operation_id="zero-fill-duplicate-id-v1",
            portfolio_id="paper-main",
            event_date="2026-08-27",
            expected_rowset_hash=before,
            fills=(),
            transition=None,
        )


def test_zero_fill_checkpoint_rejects_a_nonempty_ledger_day(tmp_path: Path) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "nonempty-zero-fill.sqlite")
    repository.append(_fill("same-day-fill"))
    expected = repository.rowset_hash()

    with pytest.raises(ValueError, match="ledger window is not empty"):
        repository.append_daily_operation(
            operation_id="zero-fill-on-filled-day-v1",
            portfolio_id="paper-main",
            event_date="2026-08-27",
            expected_rowset_hash=expected,
            fills=(),
            transition=None,
        )

    assert repository.get_daily_operation("zero-fill-on-filled-day-v1") is None
    assert tuple(item.fill_id for item in repository.list()) == ("same-day-fill",)


def test_daily_operation_rejects_a_preexisting_same_day_fill(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "nonempty-daily.sqlite")
    repository.append(_fill("foreign-same-day-fill"))
    expected = repository.rowset_hash()
    daily_fill = _fill("new-daily-fill")

    with pytest.raises(ValueError, match="daily ledger window is not empty"):
        repository.append_daily_operation(
            operation_id="daily-on-filled-day-v1",
            portfolio_id="paper-main",
            event_date="2026-08-27",
            expected_rowset_hash=expected,
            fills=(daily_fill,),
            transition=_transition((daily_fill.fill_id,)),
        )

    assert tuple(item.fill_id for item in repository.list()) == (
        "foreign-same-day-fill",
    )
    assert repository.list_transitions() == ()
    assert repository.get_daily_operation("daily-on-filled-day-v1") is None


def test_daily_operation_rejects_foreign_rowset_mutation_before_any_write(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "foreign-change.sqlite"
    daily_repository = PaperTradeLedgerRepository(db_path)
    expected = daily_repository.rowset_hash()
    PaperTradeLedgerRepository(db_path).append(_fill("foreign-fill"))

    daily_fill = _fill("daily-fill")
    with pytest.raises(ValueError, match="compare-and-swap failed"):
        daily_repository.append_daily_operation(
            operation_id="daily-after-foreign-v1",
            portfolio_id="paper-main",
            event_date=daily_fill.event_date,
            expected_rowset_hash=expected,
            fills=(daily_fill,),
            transition=_transition((daily_fill.fill_id,)),
        )

    assert tuple(item.fill_id for item in daily_repository.list()) == ("foreign-fill",)
    assert daily_repository.list_transitions() == ()
    assert daily_repository.get_daily_operation("daily-after-foreign-v1") is None


def test_daily_operation_rolls_back_fill_when_transition_insert_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "atomic-daily.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    before = repository.rowset_hash()
    connection = __import__("sqlite3").connect(db_path)
    try:
        connection.execute(
            """
            CREATE TRIGGER reject_daily_transition
            BEFORE INSERT ON paper_trade_transitions
            BEGIN
                SELECT RAISE(ABORT, 'injected transition failure');
            END
            """
        )
        connection.commit()
    finally:
        connection.close()

    fill = _fill("atomic-fill")
    with pytest.raises(ValueError):
        repository.append_daily_operation(
            operation_id="daily-atomic-failure-v1",
            portfolio_id="paper-main",
            event_date=fill.event_date,
            expected_rowset_hash=before,
            fills=(fill,),
            transition=_transition((fill.fill_id,)),
        )

    assert repository.rowset_hash() == before
    assert repository.list() == ()
    assert repository.list_transitions() == ()
    assert repository.get_daily_operation("daily-atomic-failure-v1") is None


def test_daily_operation_cas_serializes_competing_operations(tmp_path: Path) -> None:
    db_path = tmp_path / "daily-race.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    expected = repository.rowset_hash()

    def append(index: int) -> str:
        fill = _fill(f"race-fill-{index}")
        try:
            PaperTradeLedgerRepository(db_path).append_daily_operation(
                operation_id=f"race-operation-{index}",
                portfolio_id="paper-main",
                event_date=fill.event_date,
                expected_rowset_hash=expected,
                fills=(fill,),
                transition=_transition(
                    (fill.fill_id,), transition_id=f"race-transition-{index}"
                ),
            )
        except ValueError as exc:
            return str(exc)
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(append, (1, 2)))

    assert outcomes.count("committed") == 1
    assert sum("compare-and-swap failed" in item for item in outcomes) == 1
    assert len(repository.list()) == 1
    assert len(repository.list_transitions()) == 1


def test_rowset_hash_uses_one_read_snapshot_during_transition_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "rowset-snapshot.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    repository.append(_fill("rowset-existing"))
    expected_before = repository.rowset_hash()
    inserted = Event()
    commit_started = Event()
    committed = Event()
    original_hash = paper_trade_ledger_module._ledger_rowset_hash
    transition = _transition(("foreign-orphan-id",), transition_id="foreign-transition")
    writers: list[Thread] = []

    def write_transition_only() -> None:
        connection = sqlite3.connect(db_path, timeout=2)
        try:
            connection.execute("BEGIN IMMEDIATE")
            PaperTradeLedgerRepository._insert_daily_transition(connection, transition)
            inserted.set()
            commit_started.set()
            connection.commit()
            committed.set()
        finally:
            connection.close()

    def interleaved_hash(connection: sqlite3.Connection) -> str:
        fills = [
            list(row)
            for row in connection.execute(
                "SELECT " + ", ".join(paper_trade_ledger_module._PAPER_TRADE_LEDGER_ROW_COLUMNS)
                + " FROM paper_trade_ledger ORDER BY fill_id"
            ).fetchall()
        ]
        writer = Thread(target=write_transition_only)
        writers.append(writer)
        writer.start()
        assert inserted.wait(1)
        assert commit_started.wait(1)
        # 寫入者已抵達 commit；rowset_hash 的讀取交易仍固定舊 snapshot，
        # 因此此 transition 不會混入這次計算。
        assert not committed.wait(0.05)
        transitions = [
            list(row)
            for row in connection.execute(
                "SELECT "
                + ", ".join(paper_trade_ledger_module._PAPER_TRADE_TRANSITION_ROW_COLUMNS)
                + " FROM paper_trade_transitions ORDER BY transition_id"
            ).fetchall()
        ]
        return paper_trade_ledger_module._canonical_sha256(
            {
                "schema_version": paper_trade_ledger_module.PAPER_TRADE_LEDGER_ROWSET_SCHEMA_VERSION,
                "fills": fills,
                "transitions": transitions,
            }
        )

    monkeypatch.setattr(paper_trade_ledger_module, "_ledger_rowset_hash", interleaved_hash)
    observed = repository.rowset_hash()

    monkeypatch.setattr(paper_trade_ledger_module, "_ledger_rowset_hash", original_hash)
    writers[0].join(timeout=2)
    assert not writers[0].is_alive()
    assert committed.is_set()
    assert observed == expected_before
    assert repository.rowset_hash() != expected_before


def _append_exact_read_operation(
    repository: PaperTradeLedgerRepository,
    *,
    operation_id: str,
    event_date: str,
    fills: tuple[PaperTradeFill, ...],
    transition: PaperTradeTransition | None,
) -> None:
    repository.append_daily_operation(
        operation_id=operation_id,
        portfolio_id="paper-main",
        event_date=event_date,
        expected_rowset_hash=repository.rowset_hash(),
        fills=fills,
        transition=transition,
    )


def _rehash_daily_operation_after_raw_edit(
    repository: PaperTradeLedgerRepository,
    db_path: Path,
    operation_id: str,
) -> None:
    marker = repository.get_daily_operation(operation_id)
    assert marker is not None
    changed = replace(marker, rowset_hash_after=repository.rowset_hash())
    marker_sha256 = paper_trade_ledger_module._canonical_sha256(
        paper_trade_ledger_module._daily_marker_payload(changed)
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE paper_trade_daily_operations SET rowset_hash_after = ?, "
            "marker_sha256 = ? WHERE operation_id = ?",
            (changed.rowset_hash_after, marker_sha256, operation_id),
        )


def test_exact_daily_operation_reopens_historical_buy_sell_and_zero_after_append(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "exact-history.sqlite")
    buy_date = "2026-08-27"
    sell_date = "2026-08-28"
    zero_date = "2026-08-31"
    buy = replace(_fill("history-buy"), event_date=buy_date)
    buy_transition = replace(
        _transition((buy.fill_id,), transition_id="history-buy-transition"),
        event_date=buy_date,
    )
    _append_exact_read_operation(
        repository,
        operation_id="history-buy-op",
        event_date=buy_date,
        fills=(buy,),
        transition=buy_transition,
    )
    sell = replace(_fill("history-sell"), event_date=sell_date, side="sell")
    sell_transition = replace(
        _transition((sell.fill_id,), transition_id="history-sell-transition"),
        event_date=sell_date,
    )
    _append_exact_read_operation(
        repository,
        operation_id="history-sell-op",
        event_date=sell_date,
        fills=(sell,),
        transition=sell_transition,
    )
    _append_exact_read_operation(
        repository,
        operation_id="history-zero-op",
        event_date=zero_date,
        fills=(),
        transition=None,
    )

    with localcontext() as decimal_context:
        decimal_context.prec = 1
        decimal_context.Emax = 1
        decimal_context.Emin = -1
        decimal_context.traps[Inexact] = True
        buy_read = repository.read_exact_daily_operation(
            "history-buy-op", portfolio_id="paper-main", event_date=buy_date
        )
        sell_read = repository.read_exact_daily_operation(
            "history-sell-op", portfolio_id="paper-main", event_date=sell_date
        )
        zero_read = repository.read_exact_daily_operation(
            "history-zero-op", portfolio_id="paper-main", event_date=zero_date
        )

    assert buy_read.ordered_fills == (buy,)
    assert sell_read.ordered_fills == (sell,)
    assert sell_read.transition == sell_transition
    assert zero_read.ordered_fills == ()
    assert zero_read.transition is None


def test_exact_daily_operation_uses_one_begin_read_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "exact-one-begin.sqlite")
    _append_exact_read_operation(
        repository,
        operation_id="one-begin-op",
        event_date="2026-08-27",
        fills=(),
        transition=None,
    )
    statements: list[str] = []
    original_connect = repository._connect

    def tracked_connect(*, read_only: bool = False) -> sqlite3.Connection:
        connection = original_connect(read_only=read_only)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repository, "_connect", tracked_connect)
    result = repository.read_exact_daily_operation(
        "one-begin-op", portfolio_id="paper-main", event_date="2026-08-27"
    )
    assert result.marker.operation_id == "one-begin-op"
    assert sum(statement.strip().upper() == "BEGIN" for statement in statements) == 1


def test_exact_daily_operation_rejects_rehashed_marker_with_wrong_operation_sha(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wrong-operation-sha.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    _append_exact_read_operation(
        repository,
        operation_id="wrong-operation-sha-op",
        event_date="2026-08-27",
        fills=(),
        transition=None,
    )
    marker = repository.get_daily_operation("wrong-operation-sha-op")
    assert marker is not None
    changed = replace(marker, operation_sha256="sha256:" + "0" * 64)
    marker_sha256 = paper_trade_ledger_module._canonical_sha256(
        paper_trade_ledger_module._daily_marker_payload(changed)
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE paper_trade_daily_operations "
            "SET operation_sha256 = ?, marker_sha256 = ? WHERE operation_id = ?",
            (changed.operation_sha256, marker_sha256, marker.operation_id),
        )
    with pytest.raises(ValueError, match="operation hash mismatch"):
        repository.read_exact_daily_operation(
            marker.operation_id, portfolio_id="paper-main", event_date=marker.event_date
        )


def test_exact_daily_operation_rejects_rehashed_transition_fill_order_mismatch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wrong-transition-fill-ids.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    fill = _fill("transition-fill-order")
    transition = _transition((fill.fill_id,), transition_id="transition-fill-order-id")
    _append_exact_read_operation(
        repository,
        operation_id="transition-fill-order-op",
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    marker = repository.get_daily_operation("transition-fill-order-op")
    assert marker is not None
    changed_transition = replace(transition, fill_ids=("not-the-ledger-fill",))
    transition_sha256 = paper_trade_ledger_module._canonical_sha256(
        changed_transition.to_dict()
    )
    operation_payload = paper_trade_ledger_module._daily_operation_payload(
        operation_id=marker.operation_id,
        portfolio_id=marker.portfolio_id,
        event_date=marker.event_date,
        expected_rowset_hash=marker.expected_rowset_hash,
        entries=(fill,),
        transition=changed_transition,
    )
    changed = replace(
        marker,
        transition_sha256=transition_sha256,
        operation_sha256=paper_trade_ledger_module._canonical_sha256(operation_payload),
    )
    marker_sha256 = paper_trade_ledger_module._canonical_sha256(
        paper_trade_ledger_module._daily_marker_payload(changed)
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE paper_trade_transitions SET fill_ids_json = ? "
            "WHERE transition_id = ?",
            (
                paper_trade_ledger_module._canonical_transition_json(
                    list(changed_transition.fill_ids)
                ),
                changed_transition.transition_id,
            ),
        )
        connection.execute(
            "UPDATE paper_trade_daily_operations SET transition_sha256 = ?, "
            "operation_sha256 = ?, marker_sha256 = ? WHERE operation_id = ?",
            (
                changed.transition_sha256,
                changed.operation_sha256,
                marker_sha256,
                marker.operation_id,
            ),
        )
    with pytest.raises(ValueError, match="transition fill order mismatch"):
        repository.read_exact_daily_operation(
            marker.operation_id, portfolio_id="paper-main", event_date=marker.event_date
        )


def test_exact_daily_operation_rejects_rehashed_raw_fill_schema_version(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wrong-raw-fill-schema.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    fill = _fill("wrong-raw-fill-schema")
    transition = _transition((fill.fill_id,), transition_id="wrong-raw-fill-schema-t")
    _append_exact_read_operation(
        repository,
        operation_id="wrong-raw-fill-schema-op",
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE paper_trade_ledger SET schema_version = ? WHERE fill_id = ?",
            ("paper-trade-ledger.v2", fill.fill_id),
        )
    _rehash_daily_operation_after_raw_edit(
        repository, db_path, "wrong-raw-fill-schema-op"
    )

    with pytest.raises(ValueError, match="persisted fill schema version"):
        repository.read_exact_daily_operation(
            "wrong-raw-fill-schema-op",
            portfolio_id="paper-main",
            event_date=fill.event_date,
        )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("requested_quantity", 1000.5, "persisted integer is invalid"),
        ("turnover_bp", 120.5, "persisted integer is invalid"),
        ("research_only", 2, "persisted flag is invalid"),
    ],
)
def test_exact_daily_operation_rejects_rehashed_noncanonical_sqlite_primitives(
    tmp_path: Path,
    column: str,
    value: object,
    message: str,
) -> None:
    db_path = tmp_path / f"wrong-primitive-{column}.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    fill = _fill(f"wrong-primitive-{column}")
    transition = _transition((fill.fill_id,), transition_id=f"wrong-primitive-{column}-t")
    operation_id = f"wrong-primitive-{column}-op"
    _append_exact_read_operation(
        repository,
        operation_id=operation_id,
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f'UPDATE paper_trade_ledger SET "{column}" = ? WHERE fill_id = ?',
            (value, fill.fill_id),
        )
    _rehash_daily_operation_after_raw_edit(repository, db_path, operation_id)

    with pytest.raises(ValueError, match=message):
        repository.read_exact_daily_operation(
            operation_id, portfolio_id="paper-main", event_date=fill.event_date
        )


def test_exact_daily_operation_fails_closed_at_bounded_prefix_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "prefix-cap.sqlite")
    fill = _fill("prefix-cap-fill")
    transition = _transition((fill.fill_id,), transition_id="prefix-cap-transition")
    _append_exact_read_operation(
        repository,
        operation_id="prefix-cap-op",
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    monkeypatch.setattr(
        paper_trade_ledger_module, "_MAX_EXACT_READ_PREFIX_ROWS", 1
    )

    with pytest.raises(ValueError, match="rowset prefix limit exceeded"):
        repository.read_exact_daily_operation(
            "prefix-cap-op", portfolio_id="paper-main", event_date=fill.event_date
        )


def test_exact_daily_operation_rejects_foreign_portfolio_prefix_rows(
    tmp_path: Path,
) -> None:
    repository = PaperTradeLedgerRepository(tmp_path / "foreign-prefix.sqlite")
    _append_exact_read_operation(
        repository,
        operation_id="foreign-prefix-op",
        event_date="2026-08-27",
        fills=(),
        transition=None,
    )
    foreign = replace(
        _fill("foreign-prefix-fill"),
        portfolio_id="other-portfolio",
        event_date="2026-08-26",
    )
    repository.append(foreign)
    with pytest.raises(ValueError, match="foreign portfolio prefix row"):
        repository.read_exact_daily_operation(
            "foreign-prefix-op", portfolio_id="paper-main", event_date="2026-08-27"
        )


def test_exact_daily_operation_rejects_marker_fill_and_transition_tampering(
    tmp_path: Path,
) -> None:
    marker_db = tmp_path / "tampered-marker.sqlite"
    marker_repository = PaperTradeLedgerRepository(marker_db)
    _append_exact_read_operation(
        marker_repository,
        operation_id="tampered-marker-op",
        event_date="2026-08-27",
        fills=(),
        transition=None,
    )
    with sqlite3.connect(marker_db) as connection:
        connection.execute(
            "UPDATE paper_trade_daily_operations SET expected_rowset_hash = ? "
            "WHERE operation_id = ?",
            ("sha256:" + "0" * 64, "tampered-marker-op"),
        )
    with pytest.raises(ValueError, match="marker hash mismatch"):
        marker_repository.read_exact_daily_operation(
            "tampered-marker-op", portfolio_id="paper-main", event_date="2026-08-27"
        )

    fill_db = tmp_path / "tampered-fill.sqlite"
    fill_repository = PaperTradeLedgerRepository(fill_db)
    fill = _fill("tampered-fill-row")
    transition = _transition((fill.fill_id,), transition_id="tampered-fill-transition")
    _append_exact_read_operation(
        fill_repository,
        operation_id="tampered-fill-op",
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    with sqlite3.connect(fill_db) as connection:
        connection.execute(
            "UPDATE paper_trade_ledger SET commission = ? WHERE fill_id = ?",
            ("15.01", fill.fill_id),
        )
    with pytest.raises(ValueError, match="fill hash mismatch"):
        fill_repository.read_exact_daily_operation(
            "tampered-fill-op", portfolio_id="paper-main", event_date=fill.event_date
        )

    transition_db = tmp_path / "tampered-transition.sqlite"
    transition_repository = PaperTradeLedgerRepository(transition_db)
    transition_fill = _fill("tampered-transition-fill")
    transition_row = _transition(
        (transition_fill.fill_id,), transition_id="tampered-transition-row"
    )
    _append_exact_read_operation(
        transition_repository,
        operation_id="tampered-transition-op",
        event_date=transition_fill.event_date,
        fills=(transition_fill,),
        transition=transition_row,
    )
    with sqlite3.connect(transition_db) as connection:
        connection.execute(
            "UPDATE paper_trade_transitions SET pre_cash = ? WHERE transition_id = ?",
            ("1.00", transition_row.transition_id),
        )
    with pytest.raises(ValueError, match="transition hash mismatch"):
        transition_repository.read_exact_daily_operation(
            "tampered-transition-op",
            portfolio_id="paper-main",
            event_date=transition_fill.event_date,
        )


def test_exact_daily_operation_rejects_rehashed_rowset_after_mismatch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wrong-rowset-after.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    fill = _fill("wrong-rowset-after-fill")
    transition = _transition((fill.fill_id,), transition_id="wrong-rowset-after-transition")
    _append_exact_read_operation(
        repository,
        operation_id="wrong-rowset-after-op",
        event_date=fill.event_date,
        fills=(fill,),
        transition=transition,
    )
    marker = repository.get_daily_operation("wrong-rowset-after-op")
    assert marker is not None
    changed = replace(marker, rowset_hash_after="sha256:" + "0" * 64)
    marker_sha256 = paper_trade_ledger_module._canonical_sha256(
        paper_trade_ledger_module._daily_marker_payload(changed)
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE paper_trade_daily_operations SET rowset_hash_after = ?, "
            "marker_sha256 = ? WHERE operation_id = ?",
            (changed.rowset_hash_after, marker_sha256, marker.operation_id),
        )
    with pytest.raises(ValueError, match="historical rowset mismatch"):
        repository.read_exact_daily_operation(
            marker.operation_id, portfolio_id="paper-main", event_date=marker.event_date
        )


def test_exact_daily_operation_keeps_one_snapshot_during_concurrent_prior_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "concurrent-prior-append.sqlite"
    repository = PaperTradeLedgerRepository(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    _append_exact_read_operation(
        repository,
        operation_id="concurrent-snapshot-op",
        event_date="2026-08-27",
        fills=(),
        transition=None,
    )

    marker_read = Event()
    writer_committed = Event()
    writer_errors: list[BaseException] = []
    original_connect = repository._connect

    class CursorProxy:
        def __init__(self, cursor: sqlite3.Cursor, pause_after_fetch: bool) -> None:
            self._cursor = cursor
            self._pause_after_fetch = pause_after_fetch

        def _pause_if_needed(self) -> None:
            if self._pause_after_fetch:
                marker_read.set()
                if not writer_committed.wait(timeout=10):
                    raise TimeoutError("concurrent writer did not finish")

        def fetchone(self):
            row = self._cursor.fetchone()
            self._pause_if_needed()
            return row

        def fetchall(self):
            rows = self._cursor.fetchall()
            self._pause_if_needed()
            return rows

        def fetchmany(self, size: int | None = None):
            return self._cursor.fetchmany(size)

    class ConnectionProxy:
        def __init__(self, connection: sqlite3.Connection) -> None:
            object.__setattr__(self, "_connection", connection)

        def __getattr__(self, name: str):
            return getattr(self._connection, name)

        def __setattr__(self, name: str, value: object) -> None:
            if name == "_connection":
                object.__setattr__(self, name, value)
            else:
                setattr(self._connection, name, value)

        def execute(self, sql: str, parameters=()):
            cursor = self._connection.execute(sql, parameters)
            should_pause = (
                "FROM paper_trade_daily_operations" in sql
                and "WHERE operation_id = ? LIMIT 2" in sql
            )
            return CursorProxy(cursor, should_pause)

    def append_prior_fill() -> None:
        try:
            if not marker_read.wait(timeout=10):
                raise TimeoutError("reader did not pin its snapshot")
            prior = replace(_fill("concurrent-prior-fill"), event_date="2026-08-26")
            PaperTradeLedgerRepository(db_path).append(prior)
        except BaseException as error:
            writer_errors.append(error)
        finally:
            writer_committed.set()

    writer = Thread(target=append_prior_fill, daemon=True)
    writer.start()
    monkeypatch.setattr(
        repository,
        "_connect",
        lambda *, read_only=False: ConnectionProxy(
            original_connect(read_only=read_only)
        ),
    )
    observed = repository.read_exact_daily_operation(
        "concurrent-snapshot-op",
        portfolio_id="paper-main",
        event_date="2026-08-27",
    )
    writer.join(timeout=10)
    assert not writer.is_alive()
    assert writer_errors == []
    assert observed.marker.operation_id == "concurrent-snapshot-op"
    with pytest.raises(ValueError, match="historical rowset mismatch"):
        PaperTradeLedgerRepository(db_path).read_exact_daily_operation(
            "concurrent-snapshot-op",
            portfolio_id="paper-main",
            event_date="2026-08-27",
        )
