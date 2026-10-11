"""策略 Paper daily availability 公開 exact reader 的隔離契約測試。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
import json
from pathlib import Path
import sqlite3
import threading

import pytest

import app_module.strategy_paper_account_availability as availability_module
from app_module.personal_paper_store_paths import PersonalStoreCustody
from app_module.paper_trade_ledger import (
    PaperTradeDailyOperationRead,
    PaperTradeLedgerRepository,
)
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailability,
    StrategyPaperAccountAvailabilityError,
    StrategyPaperAccountCheckpointRead,
    read_exact_strategy_paper_account_availability,
    read_exact_strategy_paper_account_checkpoint,
)
from test_strategy_paper_account_daily import (
    _create_account,
    _fill_call,
    _seed_account,
    _writer,
    _zero_fill_call,
)


def _finalized_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result_id: str = "availability-public-reader",
    filled: bool = False,
) -> tuple[Path, PersonalStoreCustody, object, object, object]:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, result_id, config)
    result = (
        _fill_call(writer, binding, prior, result_id=result_id)
        if filled
        else _zero_fill_call(writer, binding, prior, result_id=result_id)
    )
    selected = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    )
    assert selected.route is not None
    return (
        store_paths.state_db,
        PersonalStoreCustody(selected.route, paths),
        selected.route,
        binding,
        result,
    )


def _checkpoint_with_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result_id: str,
    filled: bool,
) -> tuple[object, object, object, object, object]:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, result_id, config)
    result = (
        _fill_call(writer, binding, prior, result_id=result_id)
        if filled
        else _zero_fill_call(writer, binding, prior, result_id=result_id)
    )
    selected = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    )
    assert selected.route is not None
    return service, store_paths, selected.route, binding, result


def _read_exact(
    state_path: Path,
    custody: PersonalStoreCustody,
    binding: object,
    result: object,
    *,
    decision_cutoff: datetime | None = None,
) -> StrategyPaperAccountAvailability:
    with custody.read_sqlite(state_path) as connection:
        row = connection.execute(
            "SELECT receipt_json FROM strategy_paper_account_daily_receipts "
            "WHERE snapshot_id = ?",
            (result.snapshot_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row[0]))
    value = read_exact_strategy_paper_account_availability(
        custody,
        state_path,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=payload["snapshot_sha256"],
        base_receipt_sha256=result.receipt_sha256,
        decision_cutoff=decision_cutoff or datetime.now(timezone.utc),
    )
    assert isinstance(value, StrategyPaperAccountAvailability)
    return value


def test_public_availability_dto_rejects_naive_writer_clock() -> None:
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="timezone_unknown",
    ):
        StrategyPaperAccountAvailability(
            schema_version=availability_module.AVAILABILITY_SCHEMA,
            operation_id="operation",
            snapshot_id="snapshot",
            portfolio_id="portfolio",
            account_namespace="namespace",
            binding_sha256="sha256:" + "1" * 64,
            snapshot_sha256="sha256:" + "2" * 64,
            base_receipt_sha256="sha256:" + "3" * 64,
            persisted_at=datetime(2026, 8, 3, 8, 0),
            available_at=datetime(2026, 8, 3, 8, 1),
            receipt_sha256="sha256:" + "4" * 64,
        )


def test_public_exact_reader_returns_bound_clock_without_writing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    before = state_path.read_bytes()

    value = _read_exact(state_path, custody, binding, result)

    assert value.schema_version == availability_module.AVAILABILITY_SCHEMA
    assert value.operation_id == result.operation_id
    assert value.snapshot_id == result.snapshot_id
    assert value.portfolio_id == binding.portfolio_id
    assert value.account_namespace == binding.account_namespace
    assert value.binding_sha256 == binding.binding_sha256
    assert value.available_at >= value.persisted_at
    assert state_path.read_bytes() == before


def test_public_exact_reader_uses_fixed_exact_money_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch, filled=True
    )

    with localcontext(Context(prec=3)):
        value = _read_exact(state_path, custody, binding, result)

    assert value.snapshot_id == result.snapshot_id
    assert value.snapshot_sha256


@pytest.mark.parametrize("filled", [False, True])
def test_public_checkpoint_reader_returns_same_snapshot_clock_and_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filled: bool,
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    result_id = "checkpoint-reader-filled" if filled else "checkpoint-reader-zero"
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, result_id, config)
    result = (
        _fill_call(
            writer,
            binding,
            prior,
            result_id=result_id,
            low_precision=True,
        )
        if filled
        else _zero_fill_call(
            writer,
            binding,
            prior,
            result_id=result_id,
            low_precision=True,
        )
    )
    state_before = store_paths.state_db.read_bytes()
    ledger_before = store_paths.cost_ledger_db.read_bytes()

    with localcontext(Context(prec=3)):
        value = read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            decision_cutoff=datetime.now(timezone.utc),
        )

    assert isinstance(value, StrategyPaperAccountCheckpointRead)
    assert value.binding == binding
    assert value.snapshot.snapshot_id == result.snapshot_id
    assert value.snapshot.portfolio_id == binding.portfolio_id
    assert value.availability.snapshot_sha256
    assert value.availability.receipt_sha256 == result.availability_sha256
    assert value.operation_sha256
    assert value.ledger_operation.operation_id == result.operation_id
    assert value.ledger_operation.zero_fill is (not filled)
    assert len(value.ordered_fills) == (1 if filled else 0)
    assert (value.transition is not None) is filled
    assert store_paths.state_db.read_bytes() == state_before
    assert store_paths.cost_ledger_db.read_bytes() == ledger_before


@pytest.mark.parametrize(
    ("target", "expected_error"),
    [
        ("marker", "checkpoint_read_ledger_unavailable"),
        ("fill", "checkpoint_read_ledger_append_chain_mismatch"),
        ("transition", "checkpoint_read_ledger_append_chain_mismatch"),
        ("rowset_hash", "checkpoint_read_ledger_unavailable"),
    ],
)
def test_public_checkpoint_reader_rejects_ledger_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_error: str,
) -> None:
    service, store_paths, route, binding, result = _checkpoint_with_service(
        tmp_path,
        monkeypatch,
        result_id=f"ledger-tamper-{target}",
        filled=True,
    )
    ledger_io_path = PersonalStoreCustody(
        route, service.personal_paths
    ).io(store_paths.cost_ledger_db)
    connection = sqlite3.connect(ledger_io_path)
    try:
        connection.execute("PRAGMA journal_mode=MEMORY")
        if target == "marker":
            connection.execute(
                "UPDATE paper_trade_daily_operations SET marker_sha256=? "
                "WHERE operation_id=?",
                ("sha256:" + "0" * 64, result.operation_id),
            )
        elif target == "fill":
            connection.execute(
                "UPDATE paper_trade_ledger SET commission='999.99' WHERE fill_id=?",
                ("daily-fill-20260803-2330",),
            )
        elif target == "transition":
            connection.execute(
                "UPDATE paper_trade_transitions SET post_cash='1.00' "
                "WHERE transition_id=?",
                ("daily-transition-20260803",),
            )
        else:
            connection.execute(
                "UPDATE paper_trade_daily_operations SET rowset_hash_after=? "
                "WHERE operation_id=?",
                ("sha256:" + "9" * 64, result.operation_id),
            )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match=expected_error,
    ):
        read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            decision_cutoff=datetime.now(timezone.utc),
        )


def test_public_checkpoint_reader_ledger_reads_share_one_begin_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, binding, result = _checkpoint_with_service(
        tmp_path,
        monkeypatch,
        result_id="ledger-one-begin-snapshot",
        filled=True,
    )
    statements: list[tuple[int, str, bool]] = []
    original_connect = PaperTradeLedgerRepository._connect

    def tracked_connect(
        repository: PaperTradeLedgerRepository, *, read_only: bool = False
    ) -> sqlite3.Connection:
        connection = original_connect(repository, read_only=read_only)
        connection.set_trace_callback(
            lambda statement: statements.append(
                (id(connection), statement, connection.in_transaction)
            )
        )
        return connection

    monkeypatch.setattr(PaperTradeLedgerRepository, "_connect", tracked_connect)
    value = read_exact_strategy_paper_account_checkpoint(
        service,
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        decision_cutoff=datetime.now(timezone.utc),
    )

    ledger_reads = [
        (connection_id, statement, active)
        for connection_id, statement, active in statements
        if any(
            table in statement
            for table in (
                "paper_trade_daily_operations",
                "paper_trade_ledger",
                "paper_trade_transitions",
            )
        )
    ]
    assert value.ordered_fills[0].fill_id == "daily-fill-20260803-2330"
    assert len({connection_id for connection_id, _, _ in ledger_reads}) == 1
    assert len(ledger_reads) >= 8
    assert all(active for _, _, active in ledger_reads)


def test_public_checkpoint_reader_uses_one_public_ledger_result_during_concurrent_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store_paths, route, binding, result = _checkpoint_with_service(
        tmp_path,
        monkeypatch,
        result_id="ledger-concurrent-snapshot",
        filled=True,
    )
    ledger_io_path = PersonalStoreCustody(
        route, service.personal_paths
    ).io(store_paths.cost_ledger_db)
    setup = sqlite3.connect(ledger_io_path)
    try:
        setup.execute("PRAGMA journal_mode=WAL")
    finally:
        setup.close()
    original_read = PaperTradeLedgerRepository.read_exact_daily_operation
    read_started = threading.Event()
    writer_done = threading.Event()
    writer_errors: list[BaseException] = []
    read_count = 0

    def concurrent_writer() -> None:
        try:
            connection = sqlite3.connect(ledger_io_path, timeout=5)
            try:
                connection.execute(
                    "UPDATE paper_trade_ledger SET commission='999.99' WHERE fill_id=?",
                    ("daily-fill-20260803-2330",),
                )
                connection.commit()
                read_started.set()
            finally:
                connection.close()
        except BaseException as exc:
            writer_errors.append(exc)
        finally:
            writer_done.set()

    def read_then_start_writer(
        repository: PaperTradeLedgerRepository,
        operation_id: str,
        *,
        portfolio_id: str,
        event_date: str,
    ) -> PaperTradeDailyOperationRead:
        nonlocal read_count
        read_count += 1
        result_read = original_read(
            repository,
            operation_id,
            portfolio_id=portfolio_id,
            event_date=event_date,
        )
        if read_count == 1:
            thread = threading.Thread(target=concurrent_writer, daemon=True)
            thread.start()
            assert read_started.wait(timeout=3)
        return result_read

    monkeypatch.setattr(
        PaperTradeLedgerRepository,
        "read_exact_daily_operation",
        read_then_start_writer,
    )
    value = read_exact_strategy_paper_account_checkpoint(
        service,
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        decision_cutoff=datetime.now(timezone.utc),
    )
    assert value.ordered_fills[0].commission == Decimal("15.02")
    assert read_count == 1
    assert writer_done.wait(timeout=5)
    assert not writer_errors

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_read_ledger_append_chain_mismatch",
    ):
        read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            decision_cutoff=datetime.now(timezone.utc),
        )


def test_public_checkpoint_reader_rejects_wrong_exact_account_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, binding, result = _checkpoint_with_service(
        tmp_path,
        monkeypatch,
        result_id="checkpoint-wrong-route",
        filled=False,
    )
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_read_exact_binding_unavailable",
    ):
        read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace="wrong-account-namespace",
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            decision_cutoff=datetime.now(timezone.utc),
        )


def test_public_exact_reader_rejects_snapshot_weight_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch, filled=True
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "UPDATE paper_portfolio_positions SET weight_bp = weight_bp + 1 "
            "WHERE snapshot_id = ? AND stock_code = ?",
            (result.snapshot_id, "2330"),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="snapshot_position_reconciliation_mismatch",
    ):
        _read_exact(state_path, custody, binding, result)


def test_public_exact_reader_reads_base_and_companion_in_one_read_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    with custody.read_sqlite(state_path) as connection:
        row = connection.execute(
            "SELECT receipt_json FROM strategy_paper_account_daily_receipts "
            "WHERE snapshot_id = ?",
            (result.snapshot_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row[0]))
    statements: list[tuple[str, bool]] = []
    original = custody.read_sqlite

    @contextmanager
    def traced_read(path: Path):
        with original(path) as connection:
            connection.set_trace_callback(
                lambda statement: statements.append(
                    (statement, connection.in_transaction)
                )
            )
            try:
                yield connection
            finally:
                connection.set_trace_callback(None)

    monkeypatch.setattr(custody, "read_sqlite", traced_read)
    read_exact_strategy_paper_account_availability(
        custody,
        state_path,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=payload["snapshot_sha256"],
        base_receipt_sha256=result.receipt_sha256,
        decision_cutoff=datetime.now(timezone.utc),
    )

    selected = [
        (statement, active)
        for statement, active in statements
        if statement.lstrip().upper().startswith("SELECT")
        and any(
            table in statement
            for table in (
                "strategy_paper_account_daily_operations",
                "strategy_paper_account_daily_receipts",
                "paper_portfolio_snapshots",
                "paper_portfolio_positions",
                "strategy_paper_account_availability_v1",
            )
        )
    ]
    assert len(selected) >= 5
    assert all(active for _, active in selected)


def test_public_exact_reader_requires_selected_personal_account_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, _, _, binding, result = _finalized_checkpoint(tmp_path, monkeypatch)
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="exact_personal_route_required",
    ):
        read_exact_strategy_paper_account_availability(
            PersonalStoreCustody(None, None),
            state_path,
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            portfolio_id=binding.portfolio_id,
            account_namespace=binding.account_namespace,
            binding_sha256=binding.binding_sha256,
            snapshot_sha256="sha256:" + "0" * 64,
            base_receipt_sha256=result.receipt_sha256,
            decision_cutoff=datetime.now(timezone.utc),
        )


def test_public_exact_reader_rejects_state_path_outside_selected_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, custody, _, binding, result = _finalized_checkpoint(tmp_path, monkeypatch)
    other_path = tmp_path / "other.sqlite"

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="state_path_route_mismatch",
    ):
        read_exact_strategy_paper_account_availability(
            custody,
            other_path,
            operation_id=result.operation_id,
            snapshot_id=result.snapshot_id,
            portfolio_id=binding.portfolio_id,
            account_namespace=binding.account_namespace,
            binding_sha256=binding.binding_sha256,
            snapshot_sha256="sha256:" + "0" * 64,
            base_receipt_sha256=result.receipt_sha256,
            decision_cutoff=datetime.now(timezone.utc),
        )
    assert not other_path.exists()


def test_reader_rejects_unknown_base_operation_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(
            "SELECT operation_json FROM strategy_paper_account_daily_operations "
            "WHERE operation_id=?",
            (result.operation_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["unrecognized_claim"] = "future schema"
        connection.execute(
            "UPDATE strategy_paper_account_daily_operations SET operation_json=? "
            "WHERE operation_id=?",
            (availability_module._canonical_json(payload), result.operation_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="fields_unknown_or_incomplete",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_rejects_float_in_base_operation_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(
            "SELECT operation_json FROM strategy_paper_account_daily_operations "
            "WHERE operation_id=?",
            (result.operation_id,),
        ).fetchone()
        payload = json.loads(row[0])
        payload["fills"] = [{"unexpected_numeric_value": 0.1}]
        payload["ordered_fill_ids"] = ["float-probe"]
        connection.execute(
            "UPDATE strategy_paper_account_daily_operations SET operation_json=? "
            "WHERE operation_id=?",
            (availability_module._canonical_json(payload), result.operation_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="base_operation_float_forbidden",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_rejects_non_finalized_base_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "UPDATE strategy_paper_account_daily_operations SET status='PENDING' "
            "WHERE operation_id=?",
            (result.operation_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_base_identity_mismatch",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_bounds_snapshot_position_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.executemany(
            "INSERT INTO paper_portfolio_positions "
            "(snapshot_id, stock_code, quantity, mark_price, market_value, weight_bp) "
            "VALUES (?, ?, 1, '1.00', '1.00', 0)",
            (
                (result.snapshot_id, f"{index:04d}")
                for index in range(1, 10)
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="position_limit_exceeded",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_rejects_availability_schema_drift_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "ALTER TABLE strategy_paper_account_availability_v1 "
            "ADD COLUMN unreviewed_note TEXT"
        )
        connection.commit()
    finally:
        connection.close()
    before = state_path.read_bytes()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="schema_columns_mismatch",
    ):
        _read_exact(state_path, custody, binding, result)
    assert state_path.read_bytes() == before


def test_reader_rejects_base_operation_schema_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "ALTER TABLE strategy_paper_account_daily_operations "
            "ADD COLUMN unreviewed_note TEXT"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="schema_columns_mismatch:strategy_paper_account_daily_operations",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_rejects_oversized_base_json_before_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    oversized = '{"oversized":"' + ("x" * (2 * 1024 * 1024)) + '"}'
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "UPDATE strategy_paper_account_daily_operations SET operation_json=? "
            "WHERE operation_id=?",
            (oversized, result.operation_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="exceeds_size_limit",
    ):
        _read_exact(state_path, custody, binding, result)


def test_reader_rejects_snapshot_money_not_encoded_as_decimal_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, custody, _, binding, result = _finalized_checkpoint(
        tmp_path, monkeypatch
    )
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(
            "UPDATE paper_portfolio_snapshots SET cash='NaN' WHERE snapshot_id=?",
            (result.snapshot_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="snapshot_cash_invalid",
    ):
        _read_exact(state_path, custody, binding, result)
